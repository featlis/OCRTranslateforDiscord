import asyncio
import logging
import os
from pathlib import Path
import sys
import traceback

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

# Windows コンソール (cp932) での絵文字・プログレスバー出力による UnicodeEncodeError を防止
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Windows 環境で pathlib.Path.read_text() / open() が cp932 を使って UTF-8 ファイル（math_meta.json 等）を読み込めなくなる問題を防止
import builtins
import io

_orig_read_text = Path.read_text


def _safe_read_text(self, encoding=None, errors=None):
    if encoding is None:
        encoding = "utf-8"
    return _orig_read_text(self, encoding=encoding, errors=errors)


Path.read_text = _safe_read_text

_orig_io_open = io.open


def _safe_io_open(file, mode="r", buffering=-1, encoding=None, errors=None, newline=None, closefd=True, opener=None):
    if "b" not in mode and encoding is None:
        encoding = "utf-8"
    return _orig_io_open(
        file,
        mode=mode,
        buffering=buffering,
        encoding=encoding,
        errors=errors,
        newline=newline,
        closefd=closefd,
        opener=opener,
    )


io.open = _safe_io_open
builtins.open = _safe_io_open

LOG_FILE = BASE_DIR / "bot.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stderr),
        logging.FileHandler(LOG_FILE, encoding="utf-8"),
    ],
)
logger = logging.getLogger("indra-ocr-bot")


def _pause_and_exit(code: int = 1) -> None:
    print(f"\nログファイル: {LOG_FILE}")
    if os.name == "nt":
        os.system("pause")
    elif sys.stdin and sys.stdin.isatty():
        try:
            input("\nEnterキーを押すとウィンドウを閉じます...")
        except EOFError:
            pass
    sys.exit(code)


try:
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
except BaseException as import_exc:
    logger.critical("モジュール読み込み中にエラーが発生しました:\n%s", traceback.format_exc())
    _pause_and_exit(1)


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
        logger.error(
            "DISCORD_BOT_TOKEN が設定されていません。%s 内の DISCORD_BOT_TOKEN= にBotトークンを設定してください。",
            BASE_DIR / ".env",
        )
        _pause_and_exit(1)

    try:
        bot = IndraOCRBot()
        bot.run(DISCORD_BOT_TOKEN, log_handler=None)
    except BaseException as exc:
        logger.critical("Botの実行中にエラーが発生しました:\n%s", traceback.format_exc())
        _pause_and_exit(1)


if __name__ == "__main__":
    main()
