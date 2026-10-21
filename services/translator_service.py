import asyncio
import logging
import re
from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)

# インライン数式 ($...$)、インラインコード (`...`)、URLを退避するための正規表現
PROTECT_PATTERN = re.compile(r"(\$\$[\s\S]+?\$\$|\$[^$\n]+\$|`[^`\n]+`|https?://\S+)")


class MathSafeTranslatorService:
    """LaTeX数式・インラインコード・URLを保護しながら外国語・エラー文を日本語へ翻訳するサービス"""

    def __init__(self, target_lang: str = "ja"):
        self.target_lang = target_lang

    def _translate_sync(self, text: str) -> str:
        if not text.strip():
            return ""

        # 1. 数式 ($...$)・インラインコード (`...`)・URL をプレースホルダーに退避
        placeholders: list[str] = []

        def _replacer(match: re.Match) -> str:
            idx = len(placeholders)
            placeholders.append(match.group(0))
            return f"@@KEEP_{idx}@@"

        masked_text = PROTECT_PATTERN.sub(_replacer, text)

        # 2. GoogleTranslator (APIキー不要) で日本語に翻訳
        translator = GoogleTranslator(source="auto", target=self.target_lang)
        translated_text = translator.translate(masked_text[:4500]) or ""

        # 3. 退避した数式・コード・URLを元の位置に復元
        for idx, original in enumerate(placeholders):
            translated_text = re.sub(
                rf"@@\s*KEEP\s*_\s*{idx}\s*@@",
                lambda _, orig=original: orig,
                translated_text,
                flags=re.IGNORECASE,
            )

        return translated_text

    async def translate_to_japanese(self, text: str) -> str:
        """非同期スレッドで翻訳を実行"""
        return await asyncio.to_thread(self._translate_sync, text)

