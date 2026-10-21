import os
from dotenv import load_dotenv

load_dotenv()

DISCORD_BOT_TOKEN: str = os.getenv("DISCORD_BOT_TOKEN", "")
DISCORD_TEST_GUILD_ID: int | None = (
    int(os.environ["DISCORD_TEST_GUILD_ID"])
    if os.getenv("DISCORD_TEST_GUILD_ID", "").strip().isdigit()
    else None
)

OCR_THREADS: int = int(os.getenv("OCR_THREADS", "4"))
OCR_MAX_PAGES: int = int(os.getenv("OCR_MAX_PAGES", "5"))
MAX_FILE_SIZE_MB: int = int(os.getenv("MAX_FILE_SIZE_MB", "20"))
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
TARGET_LANG: str = os.getenv("TARGET_LANG", "ja")

ALLOWED_EXTENSIONS: set[str] = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf"}
DISCORD_SAFE_CHAR_LIMIT: int = 1800

