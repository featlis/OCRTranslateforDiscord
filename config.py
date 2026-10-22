import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
# スクリプトと同じディレクトリの .env を最優先で読み込む
load_dotenv(BASE_DIR / ".env", override=True)

# もしトークンが未設定またはプレースホルダーの場合、カレントディレクトリの .env もフォールバック読み込み
if not os.getenv("DISCORD_BOT_TOKEN") or os.getenv("DISCORD_BOT_TOKEN") == "your_discord_bot_token_here":
    load_dotenv(Path.cwd() / ".env", override=True)

DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "").strip()
DISCORD_TEST_GUILD_ID: int | None = (
    int(os.environ["DISCORD_TEST_GUILD_ID"].strip())
    if os.getenv("DISCORD_TEST_GUILD_ID", "").strip().isdigit()
    else None
)

OCR_THREADS: int = int(os.getenv("OCR_THREADS", "4").strip() or "4")
OCR_MAX_PAGES: int = int(os.getenv("OCR_MAX_PAGES", "5").strip() or "5")
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "20").strip() or "20")
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
TARGET_LANG: str = os.getenv("TARGET_LANG", "ja").strip() or "ja"

ALLOWED_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf"}
DISCORD_SAFE_CHAR_LIMIT: int = 1800
