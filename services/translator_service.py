import asyncio
import json
import logging
import re
import requests
from deep_translator import GoogleTranslator

logger = logging.getLogger(__name__)

# ディスプレイ数式 ($$...$$)、インライン数式 ($...$)、インラインコード (`...`)、URLを退避する正規表現
PROTECT_PATTERN = re.compile(r"(\$\$[\s\S]+?\$\$|\$[^$\n]+\$|`[^`\n]+`|https?://\S+)")

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


def _split_chunks(text: str, max_len: int = 4000) -> list[str]:
    """長文を行単位で max_len 以内のチャンクに分割する"""
    if len(text) <= max_len:
        return [text]

    chunks: list[str] = []
    current_lines: list[str] = []
    current_len = 0

    for line in text.splitlines(keepends=True):
        if len(line) > max_len:
            if current_lines:
                chunks.append("".join(current_lines))
                current_lines = []
                current_len = 0
            for i in range(0, len(line), max_len):
                chunks.append(line[i : i + max_len])
            continue

        if current_len + len(line) > max_len and current_lines:
            chunks.append("".join(current_lines))
            current_lines = [line]
            current_len = len(line)
        else:
            current_lines.append(line)
            current_len += len(line)

    if current_lines:
        chunks.append("".join(current_lines))

    return chunks


class MathSafeTranslatorService:
    """LaTeX数式・インラインコード・URLを保護しながら外国語・エラー文を日本語へ翻訳するサービス"""

    def __init__(self, target_lang: str = "ja"):
        self.target_lang = target_lang

    def _translate_via_clients5(self, chunk: str) -> str:
        """Primary: Google Translate Chrome Extension API (POST・改行保持・429回避)"""
        resp = requests.post(
            "https://clients5.google.com/translate_a/t",
            params={"client": "dict-chrome-ex", "sl": "auto", "tl": self.target_lang},
            data={"q": chunk},
            headers={"User-Agent": USER_AGENT},
            timeout=12,
        )
        resp.raise_for_status()
        data = resp.json()
        # レスポンス形式: [["翻訳文", "原文言語"]] または ["翻訳文"]
        if isinstance(data, list) and data:
            first = data[0]
            if isinstance(first, list) and first:
                return str(first[0])
            if isinstance(first, str):
                return first
        raise ValueError(f"Unexpected clients5 response format: {type(data)}")

    def _translate_via_batchexecute(self, chunk: str) -> str:
        """Fallback 1: Google Translate Web RPC (batchexecute MkEWBc)"""
        rpc_payload = json.dumps(
            [[["MkEWBc", json.dumps([[chunk, "auto", self.target_lang, True], [None]]), None, "generic"]]]
        )
        resp = requests.post(
            "https://translate.google.com/_/TranslateWebserverUi/data/batchexecute",
            data={"f.req": rpc_payload},
            headers={
                "Content-Type": "application/x-www-form-urlencoded;charset=UTF-8",
                "User-Agent": USER_AGENT,
            },
            timeout=12,
        )
        resp.raise_for_status()
        for line in resp.text.splitlines():
            if "MkEWBc" in line:
                outer = json.loads(line)
                inner = json.loads(outer[0][2])
                sentences = inner[1][0][0][5]
                return "".join(s[0] for s in sentences if s and s[0])
        raise ValueError("MkEWBc payload not found in batchexecute response")

    def _translate_via_deep_translator(self, chunk: str) -> str:
        """Fallback 2: deep-translator (GoogleTranslator)"""
        translator = GoogleTranslator(source="auto", target=self.target_lang)
        return translator.translate(chunk) or ""

    def _translate_chunk(self, chunk: str) -> str:
        last_err: Exception | None = None
        for method in (
            self._translate_via_clients5,
            self._translate_via_batchexecute,
            self._translate_via_deep_translator,
        ):
            try:
                result = method(chunk)
                if result:
                    return result
            except Exception as exc:
                last_err = exc
                logger.warning("Translator backend %s failed: %s", method.__name__, exc)
        if last_err:
            raise last_err
        return chunk

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

        # 2. チャンク単位で日本語に翻訳（マルチバックエンド＋自動フォールバック）
        chunks = _split_chunks(masked_text, max_len=4000)
        translated_chunks = [self._translate_chunk(c) for c in chunks]
        translated_text = "".join(translated_chunks)

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
