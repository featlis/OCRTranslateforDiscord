# OCRTranslateforDiscord

Discord上の画像（外国語ドキュメント・エラー画面・数式スクショ）やPDF付きメッセージを右クリック（「アプリ」メニュー）から超高速文字起こし＆日本語翻訳するBot（[datalab-to/indra](https://github.com/datalab-to/indra) 搭載）。

## 特徴

- **超高速CPU推論（GPU不要）**: ONNX Runtimeベースの `indra-ocr` により1ページ約230〜303msでテキスト・Markdown・LaTeX数式を抽出
- **2種類の右クリックメニュー**:
  - `🔍 文字起こし＆翻訳 (Indra OCR)`: 標準OCR＋ワンクリック日本語翻訳
  - `📐 数式・構造化OCR (Indra Math)`: インライン数式（`$...$`）・表・見出しを維持した構造化OCR
- **数式・コード・URL保護翻訳**: `$x^2$` 等のLaTeX数式やインラインコード・URLを壊さずに日本語へ翻訳
- **操作ボタンUI**: 「🌐 日本語に翻訳」「📄 Markdown/テキスト切替」「📢 チャンネルに共有」

## セットアップ手順

### 1. 仮想環境の作成とパッケージインストール（Python 3.10〜3.13）

```bash
python -m venv .venv
# Windows:
.venv\Scripts\activate
# macOS / Linux:
source .venv/bin/activate

pip install -U pip
pip install -r requirements.txt
```

### 2. 環境変数の設定

`.env.example` を `.env` にコピーし、Discord Bot Tokenを設定します。

```bash
cp .env.example .env
```

- `DISCORD_BOT_TOKEN`: Discord Developer Portal で発行したBotトークン
- `DISCORD_TEST_GUILD_ID`: 開発・テスト用サーバーID（指定すると右クリックメニューが即時反映されます）

### 3. Botの起動

```bash
python main.py
```
