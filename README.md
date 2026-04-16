# cti-primer

Local-first CTI PIR (Priority Intelligence Requirements) generation tool.

Inspired by [BEACON](https://github.com/sw33t-b1u/beacon), cti-primer converts
business context into actionable PIRs using local LLMs or dictionary-only mode —
no cloud services required.

## Features

- **5-step PIR pipeline**: Ingest → Element extraction → Asset mapping → Threat mapping → Risk scoring → PIR generation
- **Local LLM**: Works with LM Studio or any OpenAI-compatible API endpoint
- **Dictionary-only mode**: `--no-llm` for air-gapped environments
- **STIX 2.1**: Extract threat intelligence from PDF/URL reports
- **Web UI**: FastAPI-based review interface with CSRF protection
- **SAGE-compatible**: PIR output format compatible with SAGE analysis platform
- **GitHub integration**: Submit PIRs for review via GitHub/GHE Issues

## Quick Start

```bash
# Install
uv sync

# Generate PIR (dictionary-only)
uv run cti-primer --no-llm generate pir context.json -o pir.json

# Generate PIR (with LM Studio)
uv run cti-primer generate pir context.json -o pir.json

# Start Web UI
uv run cti-primer serve
```

## Configuration

Create `~/.config/cti-primer/config.toml`:

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

Environment variables (`CTI_PRIMER_*`) override TOML values.

## Commands

| Command | Description |
|---|---|
| `generate pir <input>` | Generate PIR from business context (.json or .md) |
| `generate assets <input>` | Generate SAGE-compatible asset inventory |
| `stix-from-report <source>` | Convert report (file/URL) to STIX 2.1 bundle |
| `validate <pir.json>` | Validate PIR output file |
| `submit <pir.json>` | Submit PIR for GitHub review |
| `serve` | Start web UI on http://localhost:8000 |

## License

Apache-2.0. Dictionary data in `schema/` derived from
[BEACON](https://github.com/sw33t-b1u/beacon) (Apache-2.0).
