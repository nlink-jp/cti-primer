# cti-primer

ローカルファーストのCTI PIR（Priority Intelligence Requirements）生成ツール。

[BEACON](https://github.com/sw33t-b1u/beacon)にインスパイアされたcti-primerは、ローカルLLMまたは辞書のみモードを使用して、ビジネスコンテキストから実用的なPIRを生成します。クラウドサービスは不要です。

## 機能

- **5段階PIRパイプライン**: 取り込み → 要素抽出 → 資産マッピング → 脅威マッピング → リスクスコアリング → PIR生成
- **ローカルLLM**: LM StudioまたはOpenAI互換APIエンドポイントで動作
- **辞書のみモード**: `--no-llm`でエアギャップ環境対応
- **STIX 2.1**: PDF/URLレポートから脅威インテリジェンスを抽出
- **Web UI**: CSRF保護付きFastAPIベースのレビューインターフェース
- **SAGE互換**: SAGE分析プラットフォーム互換のPIR出力形式
- **GitHub連携**: GitHub/GHE Issuesを通じたPIRレビューワークフロー

## クイックスタート

```bash
# インストール
uv sync

# PIR生成（辞書のみ）
uv run cti-primer --no-llm generate pir context.json -o pir.json

# PIR生成（LM Studio使用）
uv run cti-primer generate pir context.json -o pir.json

# Web UI起動
uv run cti-primer serve
```

## 設定

`~/.config/cti-primer/config.toml`を作成:

```toml
[llm]
endpoint = "http://localhost:1234/v1"
model = "google/gemma-4-26b-a4b"
api_key = ""

[sage]
api_url = "http://localhost:8080"

[github]
host = ""
token_env = "GITHUB_TOKEN"
repo = "org/repo"
```

環境変数（`CTI_PRIMER_*`）はTOMLの値をオーバーライドします。

## コマンド

| コマンド | 説明 |
|---|---|
| `generate pir <input>` | ビジネスコンテキストからPIR生成（.jsonまたは.md） |
| `generate assets <input>` | SAGE互換資産インベントリ生成 |
| `stix-from-report <source>` | レポート（ファイル/URL）をSTIX 2.1バンドルに変換 |
| `validate <pir.json>` | PIR出力ファイルの検証 |
| `submit <pir.json>` | GitHubレビューにPIRを提出 |
| `serve` | Web UIを http://localhost:8000 で起動 |

## ライセンス

Apache-2.0。`schema/`内の辞書データは
[BEACON](https://github.com/sw33t-b1u/beacon)（Apache-2.0）から派生。
