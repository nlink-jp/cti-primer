# Architecture — cti-primer

## Overview

cti-primer is a local-first CTI PIR generation tool that converts business context
into Priority Intelligence Requirements. It replicates BEACON's functionality using
local LLMs instead of Vertex AI.

## Why This Architecture

### httpx Direct Instead of OpenAI SDK

The OpenAI Python SDK introduces implicit behaviors — automatic retries with
non-configurable backoff, parameter normalization, and response validation —
that interfere with local LLM endpoints. LM Studio and other OpenAI-compatible
servers have subtle incompatibilities with these behaviors, causing intermittent
failures. By using httpx directly, we control the exact HTTP semantics and
delegate LLM-specific concerns to nlk-py modules purpose-built for local LLMs.

**Rejected alternative:** OpenAI SDK with monkey-patched retry logic — fragile
and couples us to SDK internals.

### Full Scratch vs BEACON Fork

BEACON is a moving target. Forking and maintaining a patch set introduces a
perpetual merge conflict risk, especially when upstream makes structural changes
to the LLM client layer (which is exactly the part we replace). A full rewrite
referencing BEACON's design is more maintainable.

**Rejected alternative:** Fork with Vertex AI → httpx adapter — would require
tracking every upstream change to the LLM call sites.

### LLMClient Protocol for Testability

Every module that calls an LLM accepts it as a parameter (dependency injection)
via the `LLMClient` Protocol. This means:
- Unit tests use `StubLLMClient` returning canned responses
- Integration tests use `HttpxLLMClient` with respx mocking
- `NoLLMClient` provides `--no-llm` mode with zero conditional branches in business logic

### Pure Functions in Analysis Pipeline

All five analysis modules (`element_extractor`, `asset_mapper`, `threat_mapper`,
`risk_scorer`, `pir_clusterer`) are pure functions. They receive all inputs as
parameters and return results without side effects. This makes them:
- Trivially testable without mocks
- Composable in different pipeline configurations
- Safe for concurrent execution if needed later

## Data Flow

```
Input (JSON/Markdown)
  │
  ▼
┌──────────────────┐
│  Context Parser   │── LLM (Markdown only)
│  (ingest/)        │
└────────┬─────────┘
         │ BusinessContext
         ▼
┌──────────────────┐
│ Element Extractor │── Pure function
│                   │
└────────┬─────────┘
         │ [BusinessElement] + [triggers]
         ▼
┌──────────────┐  ┌──────────────┐
│ Asset Mapper  │  │ Threat Mapper │
│ (dict + LLM) │  │ (dict + LLM)  │
└──────┬───────┘  └──────┬───────┘
       │ [AssetTag]      │ [ThreatProfile]
       └────────┬────────┘
                ▼
       ┌────────────────┐
       │  Risk Scorer    │── SAGE boost (optional)
       └────────┬───────┘
                │ [RiskScore]
                ▼
       ┌────────────────┐
       │ PIR Clusterer   │── 8 threat families, max 5 clusters
       └────────┬───────┘
                │ [ThreatCluster]
                ▼
       ┌────────────────┐
       │  PIR Builder    │── LLM augmentation (optional)
       └────────┬───────┘
                │ PIROutput
                ▼
       ┌────────────────┐
       │ Report Builder  │── Collection plan Markdown
       └────────────────┘
```

## Security Model

### Prompt Injection Defense

All LLM calls that include untrusted data (user business context, report text)
use `nlk.guard.Tag.new()` to create a cryptographically unique XML boundary per
call. The `build_guarded_prompt()` helper enforces this pattern.

### Web UI CSRF

The FastAPI web application generates per-session CSRF tokens validated on every
POST endpoint using `secrets.compare_digest()` for timing-safe comparison.

### API Key Handling

LLM API keys are stored as `pydantic.SecretStr`, which prevents accidental
logging via `__repr__`. Keys are only extracted at the HTTP request boundary.

## External Dependencies

| Dependency | Role | Failure Mode |
|---|---|---|
| Local LLM (LM Studio) | Text generation | Required unless `--no-llm` |
| SAGE API | Observation boost | Fail-open (returns 0) |
| GitHub API | Issue creation | Required for `submit` only |

## Configuration Priority

1. CLI flags / function parameters
2. Environment variables (`CTI_PRIMER_*`)
3. TOML config file (`~/.config/cti-primer/config.toml`)
4. Hardcoded defaults

## Key Metrics

- **141 unit tests** covering all modules
- **0 external cloud dependencies** in `--no-llm` mode
- **6 BEACON dictionary files** reused (Apache-2.0 attribution)
- **7 prompt templates** for LLM-assisted pipeline stages
