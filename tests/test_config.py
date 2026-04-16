"""Tests for cti_primer.config."""

from __future__ import annotations

import textwrap
from pathlib import Path

from cti_primer.config import Config, LLMConfig, SAGEConfig, load_config


class TestLoadToml:
    def test_defaults_when_no_file(self, tmp_path: Path) -> None:
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert cfg.llm.endpoint == "http://localhost:1234/v1"
        assert cfg.llm.model == "google/gemma-4-26b-a4b"
        assert cfg.llm.api_key.get_secret_value() == ""
        assert cfg.sage.api_url == "http://localhost:8080"

    def test_loads_toml_values(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "config.toml"
        toml_path.write_text(
            textwrap.dedent("""\
                [llm]
                endpoint = "http://myhost:9999/v1"
                model = "custom-model"
                api_key = "sk-test-key"

                [sage]
                api_url = "http://sage:3000"

                [github]
                host = "github.example.com"
                repo = "org/repo"
            """)
        )
        cfg = load_config(toml_path)
        assert cfg.llm.endpoint == "http://myhost:9999/v1"
        assert cfg.llm.model == "custom-model"
        assert cfg.llm.api_key.get_secret_value() == "sk-test-key"
        assert cfg.sage.api_url == "http://sage:3000"
        assert cfg.github.host == "github.example.com"
        assert cfg.github.repo == "org/repo"

    def test_partial_toml(self, tmp_path: Path) -> None:
        toml_path = tmp_path / "config.toml"
        toml_path.write_text("[llm]\nmodel = 'other-model'\n")
        cfg = load_config(toml_path)
        assert cfg.llm.model == "other-model"
        assert cfg.llm.endpoint == "http://localhost:1234/v1"
        assert cfg.sage.api_url == "http://localhost:8080"


class TestEnvOverrides:
    def test_env_overrides_toml(self, tmp_path: Path, monkeypatch: object) -> None:
        toml_path = tmp_path / "config.toml"
        toml_path.write_text("[llm]\nmodel = 'toml-model'\n")

        monkeypatch.setenv("CTI_PRIMER_LLM_MODEL", "env-model")  # type: ignore[attr-defined]
        monkeypatch.setenv("CTI_PRIMER_LLM_API_KEY", "env-key")  # type: ignore[attr-defined]
        monkeypatch.setenv("CTI_PRIMER_SAGE_API_URL", "http://env-sage:5000")  # type: ignore[attr-defined]

        cfg = load_config(toml_path)
        assert cfg.llm.model == "env-model"
        assert cfg.llm.api_key.get_secret_value() == "env-key"
        assert cfg.sage.api_url == "http://env-sage:5000"

    def test_env_config_path(self, tmp_path: Path, monkeypatch: object) -> None:
        toml_path = tmp_path / "custom.toml"
        toml_path.write_text("[llm]\nmodel = 'from-env-path'\n")

        monkeypatch.setenv("CTI_PRIMER_CONFIG", str(toml_path))  # type: ignore[attr-defined]
        cfg = load_config()
        assert cfg.llm.model == "from-env-path"


class TestConfigModels:
    def test_llm_config_defaults(self) -> None:
        cfg = LLMConfig()
        assert cfg.temperature == 0.2
        assert cfg.timeout == 120

    def test_sage_config_defaults(self) -> None:
        cfg = SAGEConfig()
        assert cfg.timeout == 5

    def test_config_serialization(self) -> None:
        cfg = Config()
        data = cfg.model_dump()
        assert "llm" in data
        assert "sage" in data
        assert "github" in data

    def test_api_key_not_in_repr(self) -> None:
        cfg = LLMConfig(api_key="secret-value")
        repr_str = repr(cfg)
        assert "secret-value" not in repr_str
