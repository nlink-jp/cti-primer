# AGENTS.md — cti-primer

## Project Summary
Local-first CTI PIR generation tool inspired by BEACON. Converts business context
into Priority Intelligence Requirements using local LLMs or dictionary-only mode.

## Build & Test
```bash
uv sync                          # Install dependencies
uv run pytest tests/ -v          # Run all tests
uv run ruff check src/ tests/    # Lint
make build                       # Build wheel to dist/
```

## Run
```bash
# Dictionary-only mode
uv run cti-primer --no-llm generate pir tests/fixtures/sample_context.json

# With LM Studio (requires running instance)
uv run cti-primer generate pir tests/fixtures/sample_context.json -o pir.json

# Web UI
uv run cti-primer serve
```

## Project Structure
```
src/cti_primer/
├── config.py           # TOML + env var config
├── models.py           # Pydantic v2 data models
├── cli.py              # Click CLI entry point
├── pipeline.py         # Pipeline orchestrator
├── llm/
│   ├── client.py       # httpx LLM client (no SDK)
│   └── prompts/        # Prompt templates (.md)
├── ingest/
│   ├── context_parser.py
│   ├── report_reader.py
│   └── stix_extractor.py
├── analysis/
│   ├── element_extractor.py
│   ├── asset_mapper.py
│   ├── threat_mapper.py
│   ├── risk_scorer.py
│   └── pir_clusterer.py
├── generator/
│   ├── pir_builder.py
│   ├── report_builder.py
│   └── assets_generator.py
├── sage/client.py      # Fail-open SAGE API client
├── review/github.py    # GitHub Issue creation
└── web/
    ├── app.py          # FastAPI application
    └── templates/      # Jinja2 templates
```

## Key Design Decisions
- httpx direct calls (no OpenAI SDK) for LLM stability with local models
- LLMClient Protocol for dependency injection and testability
- nlk-py for prompt injection defense, JSON repair, retry, validation
- All analysis modules are pure functions with explicit parameters
- SAGE integration is fail-open (pipeline continues on errors)

## Gotchas
- Schema files in schema/ are derived from BEACON (Apache-2.0)
- LLM retry tests in test_llm_client.py are slow (~60s) due to backoff sleeps
- Web UI uses in-memory session store (single-process only)
- `--no-llm` mode skips Markdown parsing and STIX extraction
