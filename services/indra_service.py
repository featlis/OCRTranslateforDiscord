from dataclasses import dataclass
from pathlib import Path
import asyncio
import logging
import threading
import indra_ocr

logger = logging.getLogger(__name__)


@dataclass
class PageOCRResult:
    page_number: int
    plain_text: str
    markdown_text: str
    source_type: str        # "ocr", "text", "hybrid", "error"
    total_ms: float
    avg_confidence: float


class IndraOCRService:
    """datalab-to/indra を非同期Botから安全に呼び出すサービスクラス"""

    def __init__(self, threads: int = 4, max_pages: int = 5):
        self.threads = threads
        self.max_pages = max_pages
        self._lock = threading.Lock()
        self._conv_standard = None
        self._conv_math = None

    def preload_models(self) -> None:
        """Bot起動時にモデルをロード（初回は約18MBのONNXモデルをHFから自動取得）"""
        logger.info("Loading Indra OCR models (threads=%d)...", self.threads)
        self._conv_standard = indra_ocr.load(
            threads=self.threads,
            mode="auto",
            math=False,
        )
        self._conv_math = indra_ocr.load(
            threads=self.threads,
            mode="auto",
            math=True,
        )
        logger.info("Indra OCR models loaded successfully.")

    def _extract_sync(self, file_path: Path, use_math: bool = False) -> list[PageOCRResult]:
        """ワーカースレッド内で同期実行されるOCR処理"""
        with self._lock:
            if self._conv_standard is None or self._conv_math is None:
                self.preload_models()

            conv = self._conv_math if use_math else self._conv_standard
            results: list[PageOCRResult] = []

            for idx, page in conv.convert(str(file_path), max_pages=self.max_pages):
                confidences = [line.conf for line in page.lines] if page.lines else []
                avg_conf = sum(confidences) / len(confidences) if confidences else 0.0
                total_ms = page.timings.get("total_ms", 0.0) if page.timings else 0.0

                results.append(
                    PageOCRResult(
                        page_number=idx + 1,
                        plain_text=page.text.strip(),
                        markdown_text=page.markdown.strip(),
                        source_type=page.source,
                        total_ms=total_ms,
                        avg_confidence=avg_conf,
                    )
                )
        return results

    async def extract_from_file(self, file_path: Path, use_math: bool = False) -> list[PageOCRResult]:
        """discord.py のイベントループをブロックせずにOCRを実行"""
        return await asyncio.to_thread(self._extract_sync, file_path, use_math)

