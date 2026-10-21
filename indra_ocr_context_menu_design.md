# Discord 右クリック文字起こし＆日本語翻訳Bot（Indra OCR搭載）基本・詳細設計書

## 1. システム概要：Indra OCRの超高速CPU推論とDiscordコンテキストメニューを統合する

本設計書は、Discord上の外国語ドキュメント・エラー画面・数式を含む画像（スクリーンショット）やPDF付きメッセージを右クリック（「アプリ」メニュー）するだけで、テキスト・数式の抽出と日本語翻訳を実行するPython製Discord Bot（`discord.py` 2.x）の設計仕様を定義します。OCRエンジンにはDatalabが公開している軽量・高速OCRライブラリ [datalab-to/indra](https://github.com/datalab-to/indra)（モデル重み：[Hugging Face datalab-to/indra-ocr](https://huggingface.co/datalab-to/indra-ocr)）を採用します。

### 1.1 Indra OCR（`indra-ocr`）の技術特性と採用メリット

[Indra公式ベンチマーク記事](https://www.datalab.to/blog/indra-ocr)および[GitHubリポジトリ](https://github.com/datalab-to/indra)で公開されている仕様に基づき、Discord Botへ組み込む際の技術的特徴を以下に整理します。

| 評価項目 | Indra OCR（v0.3.x）の仕様 | Discord Bot運用におけるメリット・影響 |
| :--- | :--- | :--- |
| **モデルサイズ・依存関係** | 約100万パラメータ（合計約18 MB）、ONNX Runtimeベース（PyTorch不要） | GPU不要。安価なVPSや小型PC・Raspberry Pi等の低メモリ環境でも常駐可能 |
| **推論速度（レイテンシ）** | 4 vCPU環境で1ページあたり中央値 **約230〜303 ms**（最大49ページ/秒） | Tesseract（約5.5秒）やPaddleOCR（約2.7秒）と比べ11〜24倍高速で、右クリック直後に結果が返る |
| **出力フォーマット** | Markdown（`page.markdown`）、プレーンテキスト（`page.text`）、矩形座標付きJSON（`page.blocks` / `page.lines`） | 見出し（`##`）・箇条書き・HTML表・LaTeX数式（`--math`有効時）を保ったままDiscordへ整形出力できる |
| **動作要件** | Python 3.10以上（Linux `x86_64` / `aarch64`, macOS Apple Silicon対応） | [pyproject.toml](https://github.com/datalab-to/indra/blob/main/pyproject.toml) の依存は `numpy`, `opencv-python-headless`, `onnxruntime`, `pypdfium2`, `huggingface_hub` のみと軽量 |
| **ライセンス** | コード：Apache-2.0 / モデル重み：Modified OpenRAIL-M | 個人利用・研究・年商/資金調達2,000万ドル未満の組織は無料で利用可能（商用API競合利用のみ制限） |

### 1.2 対象ユースケース（外国語・エラー画面・数式 → 日本語翻訳）との適合性と注意点

「画像内の文字は外国語・エラーログ・数式であり、抽出したテキストを日本語に翻訳する」という使い方は、[datalab-to/indra の仕様](https://github.com/datalab-to/indra)において**最も強みを発揮できる領域**です。実運用で意識すべき仕様上の境界線と対策は以下の通りです。

| 対象コンテンツ | Indra OCRでの抽出可否・精度 | 翻訳・抽出時の注意点と本設計での対策 |
| :--- | :--- | :--- |
| **外国語テキスト**（英語・欧州言語・中国語・ロシア語等） | **◎ 完全対応**（ラテン文字約50言語・簡体/繁体中国語・キリル文字・ギリシャ文字等に対応） | 抽出後のテキストは通常のPython文字列（`str`）になるため、翻訳モジュールへ渡せば問題なく自然な日本語へ翻訳可能（※ハングル・アラビア語・タイ語の画像のみ未対応） |
| **エラー画面・ターミナル・ログ** | **◎ 高精度で対応**（等幅フォントや記号・スタックトレースも高速にテキスト化） | エラー文を丸ごと機械翻訳すると関数名やファイルパスまで誤訳されるため、**「コピペ検索用の原文コードブロック」と「日本語訳」を上下に分けて併記**するUIとする |
| **数式（インライン数式・技術文書）** | **○ インライン数式に対応**（`math=True` で段落内の数式を `$...$` のLaTeX形式で出力） | 1. 翻訳機にそのまま通すと `$x^2$` 等のLaTeX記法が壊れるため、**正規表現で `$...$` を一時退避（マスク）して翻訳後に復元する処理**を実装する<br>2. [公式Limitations](https://github.com/datalab-to/indra)の通り、段落内のインライン数式は得意だが、複数行にわたる巨大な独立ディスプレイ数式（複雑な行列等）は崩れる場合がある |

## 2. 機能要件とUI/UX仕様：右クリックから2クリック以内で抽出・日本語翻訳を完結させる

### 2.1 コンテキストメニュー（右クリック「アプリ」）仕様

Discordの「メッセージコンテキストメニュー（`@app_commands.context_menu`）」は、1つのBotにつき最大5個まで登録可能です。用途に応じて以下の2つの右クリックメニューを実装します。

| メニュー表示名 | 対象 | 動作内容・出力形式 | デフォルト公開範囲 |
| :--- | :--- | :--- | :--- |
| **🔍 文字起こし＆翻訳 (Indra OCR)** | メッセージ | 添付画像またはPDFを `indra-ocr` で解析し、コピペしやすい原文コードブロックを表示（ボタン1つで即座に日本語翻訳を併記） | 実行者のみ表示（`ephemeral=True`） |
| **📐 数式・構造化OCR (Indra Math)** | メッセージ | `math=True` モードで解析し、数式をLaTeX（`$...$`）、見出しや表をMarkdownとして構造化抽出＋数式保護付き日本語翻訳に対応する | 実行者のみ表示（`ephemeral=True`） |

### 2.2 インタラクティブUI（実行後のアクションボタン）

文字起こし結果のメッセージ下部には、`discord.ui.View` を用いた操作ボタンを配置し、二次作業をワンクリックで行えるようにします。

| ボタンラベル | スタイル | アクション内容 |
| :--- | :--- | :--- |
| **🌐 日本語に翻訳** | `ButtonStyle.success` | LaTeX数式（`$...$`）やインラインコードを保護したまま日本語へ翻訳し、「原文＋日本語訳」を上下に並べて表示する |
| **📄 Markdown構造表示** | `ButtonStyle.secondary` | 行単位のプレーンテキスト（`page.text`）とレイアウト維持Markdown（`page.markdown`）の表示を切り替える |
| **📢 チャンネルに共有** | `ButtonStyle.primary` | 自分だけに見えている（Ephemeral）抽出結果・翻訳結果を、元メッセージへの返信としてチャンネル全員に公開する |

## 3. システムアーキテクチャと非同期処理フロー：イベントループをブロックせず3秒制限を回避する

DiscordのInteraction（右クリックメニューやスラッシュコマンド）は **「受信から3秒以内に初期応答を返さないとタイムアウトエラーになる」** という厳格な仕様があります。また、`indra-ocr` の推論や翻訳通信は同期処理を含むため、メインスレッドをブロックしない非同期設計とします。

### 3.1 処理シーケンス（ステップバイステップ）

1. **起動・モデルプリロード（Bot起動時）**
   - Bot起動時の `setup_hook` にて `indra_ocr.load(threads=4, mode="auto")` を初期化し、初回実行時のHugging Faceからのモデルダウンロード（約18MB）とONNXセッション生成を事前に済ませる。
2. **Interaction受信と即時Defer（0.1秒以内）**
   - ユーザーがメッセージを右クリックして「🔍 文字起こし＆翻訳 (Indra OCR)」を選択。
   - Botは即座に `await interaction.response.defer(ephemeral=True, thinking=True)` を返し、「Botが考えています...」状態にして応答猶予を15分間に延長する。
3. **対象メッセージの添付ファイル・埋め込み画像抽出**
   - `message.attachments` および `message.embeds`（URL貼付画像）から、対応拡張子（`.png`, `.jpg`, `.jpeg`, `.webp`, `.bmp`, `.pdf`）を取得する。
4. **一時領域への非同期ダウンロード**
   - `tempfile.TemporaryDirectory()` を作成し、`attachment.save(temp_path)` でローカルの一時ファイルへ非同期保存する（処理完了後にディレクトリごと自動削除）。
5. **ワーカースレッドでのIndra OCR推論（`asyncio.to_thread`）**
   - `await asyncio.to_thread(...)` を呼び出し、メインの非同期イベントループを止めずに別スレッドで `conv.convert(str(temp_path))` を実行する。
6. **数式・コード保護付き日本語翻訳（ボタン押下時または自動実行）**
   - 抽出テキスト内のLaTeX数式（`$...$`）を一時プレースホルダー（`@@KEEP_0@@` 等）に置換したうえで翻訳API（無料の `deep-translator` または DeepL / LLM）へ渡し、翻訳後に元のLaTeX数式を復元する。
7. **結果整形と長文フォールバック送信**
   - 抽出＋翻訳文字数が1,800文字以内の場合：原文コードブロックと日本語訳を並べて返却する。
   - 1,800文字を超える場合：Discordの2,000文字制限を回避するため、`ocr_translated_result.md` ファイル（`discord.File`）として添付送信する。

## 4. ディレクトリ構成とモジュール分割：OCR推論層と翻訳層を疎結合に保つ

```text
discord-indra-ocr-bot/
├── .env                        # Discord Bot Token 等の環境変数
├── .env.example                # 環境変数テンプレート
├── requirements.txt            # 依存パッケージ一覧
├── main.py                     # Botエントリーポイント・起動処理
├── config.py                   # 設定値管理（スレッド数・上限サイズ・対応拡張子）
├── cogs/
│   └── ocr_context_menu.py     # 右クリックメニュー定義・Embed生成・ボタンUI（View）
├── services/
│   ├── indra_service.py        # datalab-to/indra ラッパー（シングルトン＆スレッド実行）
│   └── translator_service.py   # LaTeX数式・コード保護機能付き日本語翻訳サービス
└── utils/
    └── media_extractor.py      # メッセージからの画像/PDF抽出・サイズ検証・一時保存
```

## 5. コアモジュールの実装設計とサンプルコード：そのまま動くベース実装

### 5.1 データモデルとIndra OCRサービスクラス（`services/indra_service.py`）

[datalab-to/indra の Python API](https://github.com/datalab-to/indra) に準拠し、`indra_ocr.load()` で生成したコンバータを保持して非同期スレッドから安全に呼び出す実装です。

```python
# services/indra_service.py
from dataclasses import dataclass
from pathlib import Path
import asyncio
import threading
import indra_ocr


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

    def _extract_sync(self, file_path: Path, use_math: bool = False) -> list[PageOCRResult]:
        """ワーカースレッド内で同期実行されるOCR処理"""
        if self._conv_standard is None:
            self.preload_models()

        conv = self._conv_math if use_math else self._conv_standard
        results: list[PageOCRResult] = []

        with self._lock:
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
```

### 5.2 LaTeX数式・エラー記号を壊さない日本語翻訳サービス（`services/translator_service.py`）

`indra-ocr` の `math=True` が出力する `$...$` 形式のLaTeX数式やURLが機械翻訳で崩れるのを防ぐため、プレースホルダー退避・復元を行う翻訳クラスです。

```python
# services/translator_service.py
import asyncio
import re
from deep_translator import GoogleTranslator

# インライン数式 ($...$) やURLを退避するための正規表現
PROTECT_PATTERN = re.compile(r"(\$[^$\n]+\$|https?://\S+)")


class MathSafeTranslatorService:
    """LaTeX数式やURLを保護しながら外国語・エラー文を日本語へ翻訳するサービス"""

    def __init__(self, target_lang: str = "ja"):
        self.target_lang = target_lang

    def _translate_sync(self, text: str) -> str:
        if not text.strip():
            return ""

        # 1. 数式 ($...$) と URL をプレースホルダーに退避
        placeholders: list[str] = []

        def _replacer(match: re.Match) -> str:
            idx = len(placeholders)
            placeholders.append(match.group(0))
            return f"@@KEEP_{idx}@@"

        masked_text = PROTECT_PATTERN.sub(_replacer, text)

        # 2. GoogleTranslator (APIキー不要) で日本語に翻訳
        translator = GoogleTranslator(source="auto", target=self.target_lang)
        translated_text = translator.translate(masked_text[:4500])

        # 3. 退避した数式・URLを元の位置に復元
        for idx, original in enumerate(placeholders):
            translated_text = re.sub(
                rf"@@\s*KEEP\s*_\s*{idx}\s*@@",
                lambda _: original,
                translated_text,
                flags=re.IGNORECASE,
            )

        return translated_text

    async def translate_to_japanese(self, text: str) -> str:
        """非同期スレッドで翻訳を実行"""
        return await asyncio.to_thread(self._translate_sync, text)
```

### 5.3 右クリックメニューと翻訳ボタンUIの実装（`cogs/ocr_context_menu.py`）

```python
# cogs/ocr_context_menu.py
import io
import tempfile
from pathlib import Path
import discord
from discord import app_commands
from discord.ext import commands
from services.indra_service import IndraOCRService, PageOCRResult
from services.translator_service import MathSafeTranslatorService

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".pdf"}
MAX_FILE_SIZE_BYTES = 20 * 1024 * 1024  # 20 MB上限


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
        self.translated_cache: dict[int, str] = {}
        self.show_translation = False

    def format_content(self) -> str:
        blocks = []
        for r in self.results:
            body = r.markdown_text if self.show_markdown else r.plain_text
            if not body:
                body = "（テキストが検出されませんでした）"
            header = f"--- Page {r.page_number} ({r.total_ms:.0f}ms | conf: {r.avg_confidence:.1%}) ---"
            section = f"{header}\n{body}"

            if self.show_translation and r.page_number in self.translated_cache:
                section += f"\n\n[🇯🇵 日本語訳]\n{self.translated_cache[r.page_number]}"

            blocks.append(section)
        return "\n\n".join(blocks)

    async def _update_message(self, interaction: discord.Interaction):
        content = self.format_content()
        lang_tag = "markdown" if self.show_markdown else "text"
        if len(content) <= 1800:
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
        if not self.translated_cache:
            for r in self.results:
                src = r.markdown_text if self.show_markdown else r.plain_text
                if src:
                    self.translated_cache[r.page_number] = await self.translator.translate_to_japanese(src)

        self.show_translation = not self.show_translation
        button.label = "🔤 原文のみ表示" if self.show_translation else "🌐 日本語に翻訳"
        await self._update_message(interaction)

    @discord.ui.button(label="📄 Markdown/テキスト切替", style=discord.ButtonStyle.secondary)
    async def toggle_format(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.show_markdown = not self.show_markdown
        await self._update_message(interaction)

    @discord.ui.button(label="📢 チャンネルに共有", style=discord.ButtonStyle.primary)
    async def share_to_channel(self, interaction: discord.Interaction, button: discord.ui.Button):
        content = self.format_content()
        button.disabled = True
        await interaction.response.edit_message(view=self)
        if len(content) <= 1800:
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

        valid_attachments = [
            att for att in message.attachments
            if Path(att.filename).suffix.lower() in ALLOWED_EXTENSIONS
        ]
        if not valid_attachments:
            await interaction.followup.send(
                "⚠️ このメッセージには対応する画像（PNG/JPG/WebP）またはPDFが添付されていません。",
                ephemeral=True,
            )
            return

        target_att = valid_attachments[0]
        if target_att.size > MAX_FILE_SIZE_BYTES:
            await interaction.followup.send(
                f"⚠️ ファイルサイズが上限（20MB）を超えています（{target_att.size / 1024 / 1024:.1f}MB）。",
                ephemeral=True,
            )
            return

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir) / target_att.filename
            await target_att.save(tmp_path)
            results = await self.ocr_service.extract_from_file(tmp_path, use_math=use_math)

        if not results or all(not r.plain_text for r in results):
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
        if len(formatted) <= 1800:
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
```

## 6. 非機能要件・エラーハンドリング設計：安定稼働とセキュリティを担保する

| 項目 | 設計方針・対策内容 |
| :--- | :--- |
| **Discord 3秒ルール対策** | コンテキストメニューおよび翻訳ボタンの先頭で必ず `defer()` を呼び出し、タイムアウトを防ぐ |
| **LaTeX数式・URLの翻訳破壊防止** | `MathSafeTranslatorService` にて `$...$` の数式やURLを正規表現で `@@KEEP_0@@` へ退避してから翻訳機に渡し、翻訳後に元の数式へ復元する |
| **同時実行制御（排他・並列制限）** | `indra-ocr` の `threads=4` インスタンスへの同時アクセスによるメモリスパイクを防ぐため、`threading.Lock()` で同時OCR実行数を制御する |
| **一時ファイルのクリーンアップ** | ユーザーが投稿したスクリーンショットをサーバー内に残留させないよう、Python標準の `tempfile.TemporaryDirectory()` コンテキストマネージャを使用し、例外発生時も確実に削除する |
| **長文出力制限（2,000文字上限）** | 原文＋日本語訳の合計が1,800文字を超える場合は自動でインメモリの `io.BytesIO` から `discord.File("ocr_translated_result.md")` に変換して添付返信する |

## 7. 環境構築と導入ステップ：最短10分でローカル検証を開始する

### 7.1 必要パッケージ（`requirements.txt`）

[datalab-to/indra の pyproject.toml](https://github.com/datalab-to/indra/blob/main/pyproject.toml) に定義されている依存ライブラリに加え、APIキー不要で日本語翻訳が行える `deep-translator` を追加します。

```text
discord.py>=2.4.0
indra-ocr>=0.3.1
deep-translator>=1.11.4
python-dotenv>=1.0.1
```

### 7.2 セットアップ手順

1. **Python仮想環境の作成とインストール（Python 3.10〜3.13）**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate  # Windowsの場合: .venv\Scripts\activate
   pip install -U pip
   pip install -r requirements.txt
   ```
2. **Indra OCRの単体動作確認（ローカルWebビューア）**
   - Botに組み込む前に、ターミナルで `indra-ocr-viewer --port 8765` を実行して `http://localhost:8765` を開くと、手元のエラー画面や数式スクショで認識精度や処理速度（ms）をブラウザ上で即座にテストできます。
3. **Discord Developer Portalでの設定**
   - Applicationを作成し、「Bot」タブでトークンを発行して `.env` の `DISCORD_BOT_TOKEN` に設定する。
   - 「OAuth2 > URL Generator」にて、Scopesに **`bot`** と **`applications.commands`** の2つにチェックを入れ、Permissionsで `Send Messages`, `Attach Files`, `Read Message History` を選択してサーバーへ招待する。
4. **コンテキストメニューの同期（Sync）**
   - グローバル同期（`await bot.tree.sync()`）はDiscord側のキャッシュにより反映まで最大1時間かかる場合があるため、開発中はテスト用サーバーIDを指定したギルド同期（`await bot.tree.sync(guild=discord.Object(id=GUILD_ID))`）を使用すると即座に右クリックメニューへ反映される。