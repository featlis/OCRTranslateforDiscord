import asyncio
import logging
import sys
import discord
from discord.ext import commands

from cogs.ocr_context_menu import OCRContextMenuCog
from config import (
    DISCORD_BOT_TOKEN,
    DISCORD_TEST_GUILD_ID,
    OCR_MAX_PAGES,
    OCR_THREADS,
    TARGET_LANG,
)
from services.indra_service import IndraOCRService
from services.translator_service import MathSafeTranslatorService

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("indra-ocr-bot")


class IndraOCRBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        super().__init__(command_prefix="!", intents=intents)
        self.ocr_service = IndraOCRService(threads=OCR_THREADS, max_pages=OCR_MAX_PAGES)
        self.translator_service = MathSafeTranslatorService(target_lang=TARGET_LANG)

    async def setup_hook(self) -> None:
        # 1. 起動時にIndra OCRモデル（通常モード・数式モード）をプリロード
        await asyncio.to_thread(self.ocr_service.preload_models)

        # 2. 右クリックコンテキストメニューCogを登録
        await self.add_cog(
            OCRContextMenuCog(
                bot=self,
                ocr_service=self.ocr_service,
                translator=self.translator_service,
            )
        )

        # 3. コマンドツリーを同期（テスト用サーバーID指定時は即時ギルド同期）
        if DISCORD_TEST_GUILD_ID:
            guild = discord.Object(id=DISCORD_TEST_GUILD_ID)
            self.tree.copy_global_to(guild=guild)
            synced = await self.tree.sync(guild=guild)
            logger.info("Synced %d context menu commands to guild ID %d.", len(synced), DISCORD_TEST_GUILD_ID)
        else:
            synced = await self.tree.sync()
            logger.info("Synced %d context menu commands globally.", len(synced))

    async def on_ready(self) -> None:
        if self.user:
            logger.info("Logged in as %s (ID: %d)", self.user, self.user.id)


def main() -> None:
    if not DISCORD_BOT_TOKEN or DISCORD_BOT_TOKEN == "your_discord_bot_token_here":
        logger.error("DISCORD_BOT_TOKEN が設定されていません。.env ファイルを確認してください。")
        sys.exit(1)

    bot = IndraOCRBot()
    bot.run(DISCORD_BOT_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()

