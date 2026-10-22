import io
import logging
from pathlib import Path
import tempfile
import discord
from discord import app_commands
from discord.ext import commands

from config import DISCORD_SAFE_CHAR_LIMIT
from services.indra_service import IndraOCRService, PageOCRResult
from services.translator_service import MathSafeTranslatorService
from utils.media_extractor import MediaValidationError, download_target_media

logger = logging.getLogger(__name__)


class OCRResultView(discord.ui.View):
    """文字起こし結果の下に表示する操作ボタンUI（翻訳・Markdown切替・共有）"""

    def __init__(
        self,
        results: list[PageOCRResult],
        target_message: discord.Message,
        translator: MathSafeTranslatorService,
        use_math: bool = False,
    ):
        super().__init__(timeout=300)
        self.results = results
        self.target_message = target_message
        self.translator = translator
        # 数式モード時は最初からMarkdown表示を有効化
        self.show_markdown = use_math
        self.translated_cache: dict[tuple[int, bool], str] = {}
        self.show_translation = False

    def format_content(self) -> str:
        blocks = []
        for r in self.results:
            if self.show_translation:
                body = self.translated_cache.get((r.page_number, self.show_markdown), "")
            else:
                body = r.markdown_text if self.show_markdown else r.plain_text

            if not body:
                body = "（テキストが検出されませんでした）"
            header = f"--- Page {r.page_number} ({r.total_ms:.0f}ms | conf: {r.avg_confidence:.1%}) ---"
            blocks.append(f"{header}\n{body}")
        return "\n\n".join(blocks)

    async def _ensure_translations(self) -> None:
        for r in self.results:
            key = (r.page_number, self.show_markdown)
            if key not in self.translated_cache:
                src = r.markdown_text if self.show_markdown else r.plain_text
                self.translated_cache[key] = (
                    await self.translator.translate_to_japanese(src) if src else ""
                )

    async def _update_message(self, interaction: discord.Interaction):
        content = self.format_content()
        lang_tag = "markdown" if self.show_markdown else "text"
        if len(content) <= DISCORD_SAFE_CHAR_LIMIT:
            await interaction.edit_original_response(
                content=f"```{lang_tag}\n{content}\n```",
                attachments=[],
                view=self,
            )
        else:
            buf = io.BytesIO(content.encode("utf-8"))
            await interaction.edit_original_response(
                content="📄 文字数が多いためファイルとして出力しました：",
                attachments=[discord.File(buf, filename="ocr_translated_result.md")],
                view=self,
            )

    @discord.ui.button(label="🌐 日本語に翻訳", style=discord.ButtonStyle.success)
    async def translate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if not self.show_translation:
            try:
                await self._ensure_translations()
            except Exception as exc:
                logger.exception("Translation failed: %s", exc)
                await interaction.followup.send(
                    f"⚠️ 翻訳処理中にエラーが発生しました: `{type(exc).__name__}`",
                    ephemeral=True,
                )
                return

        self.show_translation = not self.show_translation
        button.label = "🔤 原文を表示" if self.show_translation else "🌐 日本語に翻訳"
        await self._update_message(interaction)

    @discord.ui.button(label="📄 Markdown/テキスト切替", style=discord.ButtonStyle.secondary)
    async def toggle_format(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.show_markdown = not self.show_markdown
        if self.show_translation:
            try:
                await self._ensure_translations()
            except Exception as exc:
                logger.exception("Translation failed on format toggle: %s", exc)
        await self._update_message(interaction)

    @discord.ui.button(label="📢 チャンネルに共有", style=discord.ButtonStyle.primary)
    async def share_to_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        content = self.format_content()
        button.disabled = True
        await interaction.response.edit_message(view=self)
        if len(content) <= DISCORD_SAFE_CHAR_LIMIT:
            await self.target_message.reply(
                content=f"🔍 **{interaction.user.display_name}** による文字起こし結果:\n```markdown\n{content}\n```",
                mention_author=False,
            )
        else:
            buf = io.BytesIO(content.encode("utf-8"))
            await self.target_message.reply(
                content=f"🔍 **{interaction.user.display_name}** による文字起こし結果（全文ファイル）:",
                file=discord.File(buf, filename="ocr_translated_result.md"),
                mention_author=False,
            )


class OCRContextMenuCog(commands.Cog):
    def __init__(
        self,
        bot: commands.Bot,
        ocr_service: IndraOCRService,
        translator: MathSafeTranslatorService,
    ):
        self.bot = bot
        self.ocr_service = ocr_service
        self.translator = translator

        self.ocr_menu = app_commands.ContextMenu(
            name="🔍 文字起こし＆翻訳 (Indra OCR)",
            callback=self.run_standard_ocr,
        )
        self.math_ocr_menu = app_commands.ContextMenu(
            name="📐 数式・構造化OCR (Indra Math)",
            callback=self.run_math_ocr,
        )
        self.bot.tree.add_command(self.ocr_menu)
        self.bot.tree.add_command(self.math_ocr_menu)

    async def cog_unload(self) -> None:
        self.bot.tree.remove_command(self.ocr_menu.name, type=self.ocr_menu.type)
        self.bot.tree.remove_command(self.math_ocr_menu.name, type=self.math_ocr_menu.type)

    async def _process_ocr(self, interaction: discord.Interaction, message: discord.Message, use_math: bool):
        await interaction.response.defer(ephemeral=True, thinking=True)

        try:
            with tempfile.TemporaryDirectory() as tmp_dir:
                tmp_path = await download_target_media(message, Path(tmp_dir))
                results = await self.ocr_service.extract_from_file(tmp_path, use_math=use_math)
        except MediaValidationError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return
        except Exception as exc:
            logger.exception("OCR processing failed: %s", exc)
            await interaction.followup.send(
                f"❌ OCR処理中にエラーが発生しました: `{type(exc).__name__}`",
                ephemeral=True,
            )
            return

        if not results or all(not r.plain_text and not r.markdown_text for r in results):
            await interaction.followup.send(
                "🔍 文字が検出されませんでした（手書き文字や極端に不鮮明な画像、または未対応スクリプトの可能性があります）。",
                ephemeral=True,
            )
            return

        view = OCRResultView(
            results=results,
            target_message=message,
            translator=self.translator,
            use_math=use_math,
        )
        formatted = view.format_content()
        lang_tag = "markdown" if use_math else "text"
        if len(formatted) <= DISCORD_SAFE_CHAR_LIMIT:
            await interaction.followup.send(
                content=f"```{lang_tag}\n{formatted}\n```",
                view=view,
                ephemeral=True,
            )
        else:
            buf = io.BytesIO(formatted.encode("utf-8"))
            await interaction.followup.send(
                content="📄 抽出テキストが長いため、ファイルとして出力しました：",
                file=discord.File(buf, filename="ocr_translated_result.md"),
                view=view,
                ephemeral=True,
            )

    async def run_standard_ocr(self, interaction: discord.Interaction, message: discord.Message):
        await self._process_ocr(interaction, message, use_math=False)

    async def run_math_ocr(self, interaction: discord.Interaction, message: discord.Message):
        await self._process_ocr(interaction, message, use_math=True)

