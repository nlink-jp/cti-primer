# RFP: cti-primer

> Generated: 2026-04-16
> Status: Draft

## 1. Problem Statement

BEACONはビジネスコンテキストからCTI PIR（Priority Intelligence Requirements）を生成する優れたツールだが、Vertex AI（GCP）が必須で気軽に試せない。cti-primerは、ローカルLLM（LM Studio + google/gemma-4-26b-a4b）またはdictionary-onlyモードで同等の機能を提供し、GCP環境なしでPIR生成を体験・活用できるようにする。

ターゲットユーザー: 自組織内のCTIアナリスト・セキュリティチーム。外部への利用促進は想定しない。

## 2. Functional Specification

### Commands / API Surface

| コマンド | 機能 |
|---|---|
| `cti-primer generate pir <input>` | ビジネスコンテキスト → PIR生成 |
| `cti-primer generate assets <input>` | 重要資産インベントリ生成 |
| `cti-primer stix-from-report <source>` | PDF/URL → STIX 2.1バンドル変換 |
| `cti-primer validate <pir.json>` | PIR出力の検証 |
| `cti-primer submit <pir.json>` | GitHub/GHE Issueへレビュー提出 |
| `cti-primer serve` | Web UI起動（FastAPI） |

主要フラグ: `--no-llm`, `--config <path>`, `--output/-o`, `--verbose/-v`

### Input / Output

- 入力: JSON BusinessContext, Markdown戦略文書, PDF/URLレポート
- 出力: SAGE互換PIR JSON, STIX 2.1バンドル, 資産JSON, コレクションプランMarkdown

### Configuration

`~/.config/cti-primer/config.toml` + 環境変数オーバーライド

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
repo = ""
```

### External Dependencies

- ローカルLLM（LM Studio、OpenAI互換APIエンドポイント）— オプション
- GitHub/GHE（レビューワークフロー用）— オプション
- SAGE相当ツールAPI（exposure boost用）— オプション、fail-open

## 3. Design Decisions

- **Python 3.12+ / uv / hatchling** — cybersecurity-series慣例に準拠
- **httpx直接呼び出し** — OpenAI SDKの暗黙的な挙動（リトライ、パラメータ書き換え）がローカルLLMで不安定になるため不使用
- **nlk-py統合** — guard（prompt injection防御）, jsonfix（JSON修復）, backoff（リトライ）, validate（出力検証）, strip（思考タグ除去）
- **フルスクラッチ実装** — BEACONのフォークではなく、設計を参考にした独自実装。アップストリーム追従コスト排除
- **辞書データ**: BEACONから流用（Apache-2.0帰属表記）
- **セキュリティファースト**: nlk.guardでLLM呼び出し防御、CSRF on Web UI、Pydanticバリデーション
- **テスタビリティ重視**: LLMClient Protocol + 依存性注入、全分析モジュールは純関数

## 4. Development Plan

### Phase 1: Core
- config.toml + 環境変数
- Pydantic v2データモデル（BusinessContext, PIROutput）
- httpx LLMクライアント + nlk統合
- 5段階分析パイプライン
- PIR/レポート/資産生成
- CLI（generate, validate）
- テスト一式

### Phase 2: Features
- STIX from Report（PDF/URL → STIX 2.1）
- Web UI（FastAPI + Jinja2、BEACON互換ルート）
- SAGE API連携（fail-open）
- GitHub Issue連携
- submit / serve CLIコマンド

### Phase 3: Release
- README.md / README.ja.md
- CHANGELOG.md / AGENTS.md
- E2Eテスト

## 5. Required API Scopes / Permissions

- GitHub API: `repo` スコープ（Issue作成用、オプション）
- ローカルLLM: API-KEY認証対応（オプション）
- GCP/クラウド: なし

## 6. Series Placement

Series: cybersecurity-series
Reason: CTI/PIR生成はセキュリティドメインのツール。lite-seriesはローカルLLM対話ツール群で性質が異なる。

## 7. External Platform Constraints

- LM Studio: コンテキスト長はモデルとVRAM依存（gemma-4-27bで8k〜32k程度）
- PDF読み込み: pypdfライブラリ依存
- GitHub API: rate limit 5000 req/hour（認証時）

---

## Discussion Log

1. **ツール名称**: BEACONの名称は「外部にビーコンを発する」印象があるため、機能を素直に表す「cti-primer」に決定
2. **シリーズ配置**: lite-seriesではなくcybersecurity-seriesに配置（セキュリティドメイン）
3. **LLMバックエンド**: OpenAI SDK不使用 — 暗黙的挙動がローカルLLMで不安定になるため、httpx直接呼び出し + nlk-pyで対応
4. **フォーク vs スクラッチ**: フルスクラッチを選択 — アップストリーム破壊的変更リスクを排除
5. **辞書データ**: BEACONから流用（Apache-2.0帰属表記）
6. **モデル選択**: 単一モデル（google/gemma-4-26b-a4b）— ローカルではモデル切替にコストがかかるため
7. **LM Studio想定**: デフォルトエンドポイント localhost:1234
8. **API-KEY対応**: LM Studioのトークン認証に対応
9. **SAGE連携**: 別途SAGE相当ツールも開発予定、連携を前提とした設計
10. **Web UI/GitHub連携**: BEACON互換を維持
