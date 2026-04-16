# RFP: cti-primer

> Generated: 2026-04-16
> Status: Draft

## 1. Problem Statement

BEACON is an excellent tool for generating CTI PIRs (Priority Intelligence Requirements) from business context, but it requires Vertex AI (GCP), making it difficult to try casually. cti-primer provides equivalent functionality using local LLMs (LM Studio + google/gemma-4-26b-a4b) or dictionary-only mode, enabling PIR generation without a GCP environment.

Target users: Internal CTI analysts and security teams. Not intended for external promotion.

## 2. Functional Specification

### Commands / API Surface

| Command | Function |
|---|---|
| `cti-primer generate pir <input>` | Business context → PIR generation |
| `cti-primer generate assets <input>` | Critical asset inventory generation |
| `cti-primer stix-from-report <source>` | PDF/URL → STIX 2.1 bundle conversion |
| `cti-primer validate <pir.json>` | PIR output validation |
| `cti-primer submit <pir.json>` | Submit for review via GitHub/GHE Issues |
| `cti-primer serve` | Start Web UI (FastAPI) |

Key flags: `--no-llm`, `--config <path>`, `--output/-o`, `--verbose/-v`

### Input / Output

- Input: JSON BusinessContext, Markdown strategy documents, PDF/URL reports
- Output: SAGE-compatible PIR JSON, STIX 2.1 bundles, asset JSON, collection plan Markdown

### Configuration

`~/.config/cti-primer/config.toml` + environment variable overrides

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

- Local LLM (LM Studio, OpenAI-compatible API endpoint) — optional
- GitHub/GHE (review workflow) — optional
- SAGE-equivalent tool API (exposure boost) — optional, fail-open

## 3. Design Decisions

- **Python 3.12+ / uv / hatchling** — follows cybersecurity-series conventions
- **Direct httpx calls** — OpenAI SDK's implicit behaviors (retry, parameter rewriting) are unstable with local LLMs
- **nlk-py integration** — guard (prompt injection defense), jsonfix (JSON repair), backoff (retry), validate (output validation), strip (thinking tag removal)
- **Full scratch implementation** — not a BEACON fork; inspired by its design but independently implemented to avoid upstream breakage risk
- **Dictionary data**: Copied from BEACON (Apache-2.0 attribution)
- **Security-first**: nlk.guard for all LLM calls, CSRF on Web UI, Pydantic validation
- **Testability-first**: LLMClient Protocol + dependency injection, all analysis modules are pure functions

## 4. Development Plan

### Phase 1: Core
- config.toml + environment variables
- Pydantic v2 data models (BusinessContext, PIROutput)
- httpx LLM client + nlk integration
- 5-step analysis pipeline
- PIR/report/asset generation
- CLI (generate, validate)
- Full test suite

### Phase 2: Features
- STIX from Report (PDF/URL → STIX 2.1)
- Web UI (FastAPI + Jinja2, BEACON-compatible routes)
- SAGE API integration (fail-open)
- GitHub Issue integration
- submit / serve CLI commands

### Phase 3: Release
- README.md / README.ja.md
- CHANGELOG.md / AGENTS.md
- E2E testing

## 5. Required API Scopes / Permissions

- GitHub API: `repo` scope (for Issue creation, optional)
- Local LLM: API-KEY authentication support (optional)
- GCP/Cloud: None

## 6. Series Placement

Series: cybersecurity-series
Reason: CTI/PIR generation is a security domain tool. lite-series is for local-first LLM interaction tools, which is a different scope.

## 7. External Platform Constraints

- LM Studio: Context length depends on model and VRAM (gemma-4-27b: ~8k-32k tokens)
- PDF reading: pypdf library dependency
- GitHub API: rate limit 5000 req/hour (authenticated)

---

## Discussion Log

1. **Tool name**: BEACON's name suggests "emitting a beacon externally", so chose "cti-primer" which directly describes its function
2. **Series placement**: cybersecurity-series (not lite-series) as it's a security domain tool
3. **LLM backend**: No OpenAI SDK — implicit behaviors are unstable with local LLMs; direct httpx + nlk-py instead
4. **Fork vs scratch**: Full scratch to avoid upstream breaking change risk
5. **Dictionary data**: Copied from BEACON with Apache-2.0 attribution
6. **Model selection**: Single model (google/gemma-4-26b-a4b) — model switching is costly on local hardware
7. **LM Studio target**: Default endpoint localhost:1234
8. **API-KEY support**: For LM Studio token authentication
9. **SAGE integration**: A SAGE-equivalent tool will also be developed; designed for integration
10. **Web UI/GitHub integration**: Maintains BEACON compatibility
