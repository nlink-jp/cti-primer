# アーキテクチャ — cti-primer

## 概要

cti-primerは、ビジネスコンテキストからPriority Intelligence Requirements（PIR）を生成する
ローカルファーストCTIツール。Vertex AIの代わりにローカルLLMを使用してBEACONの機能を再現する。

## なぜこのアーキテクチャか

### OpenAI SDKではなくhttpx直接呼び出し

OpenAI Python SDKは暗黙的な挙動を導入する — 設定不能なバックオフによる自動リトライ、
パラメータの正規化、レスポンス検証 — これらがローカルLLMエンドポイントと干渉する。
LM Studioなどのサーバーはこれらの挙動と微妙な非互換性があり、間欠的な障害を引き起こす。
httpxを直接使用することでHTTPセマンティクスを正確に制御し、LLM固有の懸念は
ローカルLLM向けに設計されたnlk-pyモジュールに委譲する。

**却下した代替案:** OpenAI SDKのリトライロジックをモンキーパッチ — SDK内部に依存し脆弱。

### BEACONフォークではなくフルスクラッチ

BEACONは変化し続けるプロジェクトである。フォークしてパッチセットを維持すると、
特に我々が置き換えるLLMクライアント層でアップストリームが構造的変更を行った際に
永続的なマージコンフリクトリスクが生じる。BEACONの設計を参考にしたフルリライトの方が保守性が高い。

**却下した代替案:** Vertex AI → httpxアダプタ付きフォーク — LLM呼び出し箇所の上流変更を全て追跡する必要あり。

### テスタビリティのためのLLMClient Protocol

LLMを呼び出す全モジュールは`LLMClient` Protocolを通じてパラメータとして受け取る（依存性注入）:
- ユニットテストはcannedレスポンスを返す`StubLLMClient`を使用
- インテグレーションテストはrespxモック付き`HttpxLLMClient`を使用
- `NoLLMClient`はビジネスロジックに条件分岐なしで`--no-llm`モードを提供

### 分析パイプラインの純関数設計

5つの分析モジュール（`element_extractor`, `asset_mapper`, `threat_mapper`,
`risk_scorer`, `pir_clusterer`）は全て純関数。全入力をパラメータで受け取り、
副作用なしに結果を返す:
- モックなしでテスト可能
- 異なるパイプライン構成で合成可能
- 将来必要になった場合に並行実行も安全

## データフロー

```
入力 (JSON/Markdown)
  │
  ▼
┌──────────────────┐
│  Context Parser   │── LLM (Markdownのみ)
│  (ingest/)        │
└────────┬─────────┘
         │ BusinessContext
         ▼
┌──────────────────┐
│ Element Extractor │── 純関数
│                   │
└────────┬─────────┘
         │ [BusinessElement] + [triggers]
         ▼
┌──────────────┐  ┌──────────────┐
│ Asset Mapper  │  │ Threat Mapper │
│ (辞書 + LLM) │  │ (辞書 + LLM)  │
└──────┬───────┘  └──────┬───────┘
       │ [AssetTag]      │ [ThreatProfile]
       └────────┬────────┘
                ▼
       ┌────────────────┐
       │  Risk Scorer    │── SAGEブースト（オプション）
       └────────┬───────┘
                │ [RiskScore]
                ▼
       ┌────────────────┐
       │ PIR Clusterer   │── 8脅威ファミリ, 最大5クラスタ
       └────────┬───────┘
                │ [ThreatCluster]
                ▼
       ┌────────────────┐
       │  PIR Builder    │── LLM拡張（オプション）
       └────────┬───────┘
                │ PIROutput
                ▼
       ┌────────────────┐
       │ Report Builder  │── コレクションプランMarkdown
       └────────────────┘
```

## セキュリティモデル

### プロンプトインジェクション防御

非信頼データ（ユーザーのビジネスコンテキスト、レポートテキスト）を含む全LLM呼び出しは
`nlk.guard.Tag.new()`を使用して呼び出しごとに暗号的に一意なXML境界を作成する。
`build_guarded_prompt()`ヘルパーがこのパターンを強制する。

### Web UI CSRF

FastAPI WebアプリケーションはセッションごとのCSRFトークンを生成し、
全POSTエンドポイントで`secrets.compare_digest()`によるタイミングセーフな比較で検証する。

### APIキー管理

LLM APIキーは`pydantic.SecretStr`として保存され、`__repr__`による偶発的なログ出力を防止する。
キーはHTTPリクエスト境界でのみ展開される。

## 外部依存関係

| 依存先 | 役割 | 障害時の挙動 |
|---|---|---|
| ローカルLLM (LM Studio) | テキスト生成 | `--no-llm`以外では必須 |
| SAGE API | 観測ブースト | Fail-open（0を返却） |
| GitHub API | Issue作成 | `submit`コマンドでのみ必須 |

## 設定優先順位

1. CLIフラグ / 関数パラメータ
2. 環境変数（`CTI_PRIMER_*`）
3. TOMLコンフィグファイル（`~/.config/cti-primer/config.toml`）
4. ハードコードされたデフォルト値

## 主要指標

- **141ユニットテスト** — 全モジュールをカバー
- **外部クラウド依存ゼロ** — `--no-llm`モードで完全ローカル動作
- **BEACON辞書ファイル6個** — 再利用（Apache-2.0帰属表記）
- **プロンプトテンプレート7個** — LLM支援パイプライン各段階用
