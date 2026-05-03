# Changelog

## [0.1.1] - 2026-05-03

### Fixed

- Pin nlk-py to v0.2.2 to pick up the strip fix: think-tag handling
  no longer truncates LLM responses that explain the literal
  `<think>` tag inside a markdown inline-code span.

## [0.1.0] - 2026-04-16

### Added
- 5-step PIR generation pipeline (ingest → elements → assets → threats → risk → PIR)
- `--no-llm` dictionary-only mode
- httpx-based LLM client for OpenAI-compatible APIs (LM Studio)
- API-KEY authentication support
- nlk-py integration (guard, jsonfix, backoff, validate, strip)
- STIX 2.1 extraction from PDF/URL/text reports
- FastAPI Web UI with CSRF protection (BEACON-compatible routes)
- SAGE API client (fail-open)
- GitHub/GHE Issue creation for PIR review workflow
- CLI: generate pir, generate assets, stix-from-report, validate, submit, serve
- TOML configuration (`~/.config/cti-primer/config.toml`) with env var overrides
- BEACON dictionary data (threat_taxonomy, asset_tags, trigger_keywords)
- 141 unit tests
