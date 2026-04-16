"""Configuration management for cti-primer.

Priority: env vars > config.toml > defaults.
"""

from __future__ import annotations

import os
import tomllib
from pathlib import Path
from typing import Any

from pydantic import BaseModel, SecretStr

_TOOL_NAME = "cti-primer"
_ENV_PREFIX = "CTI_PRIMER_"


class LLMConfig(BaseModel):
    """LLM endpoint configuration."""

    endpoint: str = "http://localhost:1234/v1"
    model: str = "google/gemma-4-26b-a4b"
    api_key: SecretStr = SecretStr("")
    temperature: float = 0.2
    timeout: int = 120


class SAGEConfig(BaseModel):
    """SAGE API configuration."""

    api_url: str = "http://localhost:8080"
    timeout: int = 5


class GitHubConfig(BaseModel):
    """GitHub/GHE configuration."""

    host: str = ""
    token_env: str = "GITHUB_TOKEN"
    repo: str = ""


class Config(BaseModel):
    """Top-level configuration."""

    llm: LLMConfig = LLMConfig()
    sage: SAGEConfig = SAGEConfig()
    github: GitHubConfig = GitHubConfig()


def _load_toml(path: Path | None = None) -> dict[str, Any]:
    """Load TOML config file.

    Args:
        path: Explicit path. Falls back to ~/.config/cti-primer/config.toml.

    Returns:
        Parsed TOML as nested dict, or empty dict if file not found.
    """
    if path is None:
        path = Path.home() / ".config" / _TOOL_NAME / "config.toml"
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def _apply_env_overrides(cfg: Config) -> Config:
    """Apply CTI_PRIMER_* environment variable overrides.

    Supported variables:
        CTI_PRIMER_LLM_ENDPOINT
        CTI_PRIMER_LLM_MODEL
        CTI_PRIMER_LLM_API_KEY
        CTI_PRIMER_LLM_TEMPERATURE
        CTI_PRIMER_LLM_TIMEOUT
        CTI_PRIMER_SAGE_API_URL
        CTI_PRIMER_SAGE_TIMEOUT
        CTI_PRIMER_GITHUB_HOST
        CTI_PRIMER_GITHUB_TOKEN_ENV
        CTI_PRIMER_GITHUB_REPO
    """
    env = os.environ.get

    llm_data = cfg.llm.model_dump()
    sage_data = cfg.sage.model_dump()
    github_data = cfg.github.model_dump()

    _map = {
        "llm": {
            "endpoint": env(f"{_ENV_PREFIX}LLM_ENDPOINT"),
            "model": env(f"{_ENV_PREFIX}LLM_MODEL"),
            "api_key": env(f"{_ENV_PREFIX}LLM_API_KEY"),
            "temperature": env(f"{_ENV_PREFIX}LLM_TEMPERATURE"),
            "timeout": env(f"{_ENV_PREFIX}LLM_TIMEOUT"),
        },
        "sage": {
            "api_url": env(f"{_ENV_PREFIX}SAGE_API_URL"),
            "timeout": env(f"{_ENV_PREFIX}SAGE_TIMEOUT"),
        },
        "github": {
            "host": env(f"{_ENV_PREFIX}GITHUB_HOST"),
            "token_env": env(f"{_ENV_PREFIX}GITHUB_TOKEN_ENV"),
            "repo": env(f"{_ENV_PREFIX}GITHUB_REPO"),
        },
    }

    for key, val in _map["llm"].items():
        if val is not None:
            llm_data[key] = val
    for key, val in _map["sage"].items():
        if val is not None:
            sage_data[key] = val
    for key, val in _map["github"].items():
        if val is not None:
            github_data[key] = val

    return Config(
        llm=LLMConfig(**llm_data),
        sage=SAGEConfig(**sage_data),
        github=GitHubConfig(**github_data),
    )


def load_config(path: Path | None = None) -> Config:
    """Load config with priority: env vars > TOML > defaults.

    Args:
        path: Explicit config file path. If None, checks CTI_PRIMER_CONFIG
              env var, then falls back to ~/.config/cti-primer/config.toml.

    Returns:
        Fully resolved Config instance.
    """
    if path is None:
        env_path = os.environ.get(f"{_ENV_PREFIX}CONFIG")
        if env_path:
            path = Path(env_path)

    data = _load_toml(path)

    cfg = Config(
        llm=LLMConfig(**data.get("llm", {})),
        sage=SAGEConfig(**data.get("sage", {})),
        github=GitHubConfig(**data.get("github", {})),
    )

    return _apply_env_overrides(cfg)
