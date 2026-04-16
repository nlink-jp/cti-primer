"""Tests for cti_primer.pipeline and cti_primer.cli."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from cti_primer.cli import main
from cti_primer.config import Config
from cti_primer.pipeline import run_assets_pipeline, run_pipeline

FIXTURES = Path(__file__).parent / "fixtures"


class TestPipeline:
    def test_full_pipeline_no_llm(self) -> None:
        config = Config()
        result = run_pipeline(
            FIXTURES / "sample_context.json",
            config,
            no_llm=True,
        )
        assert result.context.organization.name == "Acme Manufacturing Co."
        assert len(result.elements) > 0
        assert len(result.triggers) > 0
        assert len(result.assets) > 0
        assert len(result.threats) > 0
        assert len(result.scores) > 0
        assert len(result.clusters) > 0
        assert result.pir.organization == "Acme Manufacturing Co."
        assert "# Collection Plan" in result.report

    def test_pipeline_generates_pirs(self) -> None:
        config = Config()
        result = run_pipeline(
            FIXTURES / "sample_context.json",
            config,
            no_llm=True,
        )
        # Manufacturing + JP + critical crown jewels should produce PIRs
        assert len(result.pir.pir_items) > 0

    def test_assets_pipeline_no_llm(self) -> None:
        config = Config()
        result = run_assets_pipeline(
            FIXTURES / "sample_context.json",
            config,
            no_llm=True,
        )
        assert result["organization"] == "Acme Manufacturing Co."
        assert len(result["assets"]) == 3


class TestCLI:
    def test_generate_pir_no_llm(self, tmp_path: Path) -> None:
        out = tmp_path / "pir.json"
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--no-llm",
                "generate",
                "pir",
                str(FIXTURES / "sample_context.json"),
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = json.loads(out.read_text())
        assert "pir_items" in data

    def test_generate_pir_stdout(self) -> None:
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--no-llm",
                "generate",
                "pir",
                str(FIXTURES / "sample_context.json"),
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "organization" in data

    def test_generate_assets_no_llm(self, tmp_path: Path) -> None:
        out = tmp_path / "assets.json"
        runner = CliRunner()
        result = runner.invoke(
            main,
            [
                "--no-llm",
                "generate",
                "assets",
                str(FIXTURES / "sample_context.json"),
                "-o",
                str(out),
            ],
        )
        assert result.exit_code == 0, result.output
        assert out.exists()
        data = json.loads(out.read_text())
        assert "assets" in data

    def test_validate_valid_file(self, tmp_path: Path) -> None:
        # First generate a PIR file
        out = tmp_path / "pir.json"
        runner = CliRunner()
        runner.invoke(
            main,
            [
                "--no-llm",
                "generate",
                "pir",
                str(FIXTURES / "sample_context.json"),
                "-o",
                str(out),
            ],
        )
        # Then validate it
        result = runner.invoke(main, ["validate", str(out)])
        assert result.exit_code == 0
        assert "Valid PIR output" in result.output

    def test_validate_invalid_file(self, tmp_path: Path) -> None:
        bad = tmp_path / "bad.json"
        bad.write_text('{"not": "valid pir"}')
        runner = CliRunner()
        result = runner.invoke(main, ["validate", str(bad)])
        assert result.exit_code == 1

    def test_help(self) -> None:
        runner = CliRunner()
        result = runner.invoke(main, ["--help"])
        assert result.exit_code == 0
        assert "cti-primer" in result.output
