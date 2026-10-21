from pathlib import Path
from urllib.parse import urlparse
import aiohttp
import discord

from config import ALLOWED_EXTENSIONS, MAX_FILE_SIZE_BYTES, MAX_FILE_SIZE_MB


class MediaValidationError(Exception):
    """添付ファイルまたは埋め込み画像の検証エラー"""


def _extract_extension_from_url(url: str) -> str:
    parsed = urlparse(url)
    return Path(parsed.path).suffix.lower()


async def download_target_media(message: discord.Message, tmp_dir: Path) -> Path:
    """
    メッセージの attachments または embeds から対応する画像/PDFを検証し、
    tmp_dir 内に非同期保存してファイルパスを返す。
    """
    # 1. message.attachments を優先チェック
    valid_attachments = [
        att
        for att in message.attachments
        if Path(att.filename).suffix.lower() in ALLOWED_EXTENSIONS
    ]
    if valid_attachments:
        target_att = valid_attachments[0]
        if target_att.size > MAX_FILE_SIZE_BYTES:
            size_mb = target_att.size / 1024 / 1024
            raise MediaValidationError(
                f"⚠️ ファイルサイズが上限（{MAX_FILE_SIZE_MB}MB）を超えています（{size_mb:.1f}MB）。"
            )
        tmp_path = tmp_dir / Path(target_att.filename).name
        await target_att.save(tmp_path)
        return tmp_path

    # 2. message.embeds 内の画像URLをチェック
    for embed in message.embeds:
        candidates = [
            embed.image.url if embed.image else None,
            embed.thumbnail.url if embed.thumbnail else None,
            embed.url,
        ]
        for url in candidates:
            if not url:
                continue
            ext = _extract_extension_from_url(url)
            if ext in ALLOWED_EXTENSIONS:
                tmp_path = tmp_dir / f"embed_media{ext}"
                async with aiohttp.ClientSession() as session:
                    async with session.get(url) as resp:
                        if resp.status != 200:
                            continue
                        content_length = resp.headers.get("Content-Length")
                        if content_length and int(content_length) > MAX_FILE_SIZE_BYTES:
                            size_mb = int(content_length) / 1024 / 1024
                            raise MediaValidationError(
                                f"⚠️ ファイルサイズが上限（{MAX_FILE_SIZE_MB}MB）を超えています（{size_mb:.1f}MB）。"
                            )
                        data = await resp.read()
                        if len(data) > MAX_FILE_SIZE_BYTES:
                            size_mb = len(data) / 1024 / 1024
                            raise MediaValidationError(
                                f"⚠️ ファイルサイズが上限（{MAX_FILE_SIZE_MB}MB）を超えています（{size_mb:.1f}MB）。"
                            )
                        tmp_path.write_bytes(data)
                        return tmp_path

    raise MediaValidationError(
        "⚠️ このメッセージには対応する画像（PNG/JPG/WebP/BMP）またはPDFが添付されていません。"
    )

