"""Tests for cti_primer.ingest.context_parser."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cti_primer.ingest.context_parser import ParseError, parse_file, parse_json, parse_markdown
from cti_primer.llm.client import LLMError

FIXTURES = Path(__file__).parent / "fixtures"


class StubLLMClient:
    """Test stub that returns predefined JSON."""

    def __init__(self, response: dict[str, Any]) -> None:
        self._response = response
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return json.dumps(self._response)

    def complete_json(self, system: str, user: str) -> Any:
        self.calls.append((system, user))
        return self._response


class TestParseJson:
    def test_valid_json(self) -> None:
        raw = (FIXTURES / "sample_context.json").read_text()
        ctx = parse_json(raw)
        assert ctx.organization.name == "Acme Manufacturing Co."
        assert "JP" in ctx.organization.geography
        assert len(ctx.crown_jewels) == 3

    def test_invalid_json(self) -> None:
        with pytest.raises(ParseError, match="Invalid JSON"):
            parse_json("not json at all")

    def test_missing_required_field(self) -> None:
        with pytest.raises(ParseError, match="Schema validation"):
            parse_json('{"no_organization": true}')

    def test_minimal_json(self) -> None:
        raw = json.dumps(
            {
                "organization": {
                    "name": "Test",
                    "industry": "technology",
                }
            }
        )
        ctx = parse_json(raw)
        assert ctx.organization.name == "Test"
        assert ctx.projects == []


class TestParseMarkdown:
    def test_with_stub_llm(self) -> None:
        llm = StubLLMClient(
            {
                "organization": {
                    "name": "Acme",
                    "industry": "manufacturing",
                    "geography": ["JP"],
                },
            }
        )
        ctx = parse_markdown("# Strategy Doc\nSome content", llm)
        assert ctx.organization.name == "Acme"
        assert len(llm.calls) == 1

    def test_llm_returns_invalid_schema(self) -> None:
        llm = StubLLMClient({"bad": "data"})
        with pytest.raises(ParseError, match="LLM output validation"):
            parse_markdown("# Doc", llm)

    def test_llm_failure(self) -> None:
        class FailingLLM:
            def complete(self, system: str, user: str) -> str:
                raise LLMError("connection refused")

            def complete_json(self, system: str, user: str) -> Any:
                raise LLMError("connection refused")

        with pytest.raises(ParseError, match="LLM structuring failed"):
            parse_markdown("# Doc", FailingLLM())


class TestParseFile:
    def test_json_file(self) -> None:
        ctx = parse_file(FIXTURES / "sample_context.json")
        assert ctx.organization.industry == "manufacturing"

    def test_md_file_with_llm(self) -> None:
        llm = StubLLMClient(
            {
                "organization": {"name": "Test", "industry": "tech"},
            }
        )
        ctx = parse_file(FIXTURES / "sample_context.md", llm=llm)
        assert ctx.organization.name == "Test"

    def test_md_file_without_llm_raises(self) -> None:
        with pytest.raises(ParseError, match="requires LLM"):
            parse_file(FIXTURES / "sample_context.md", llm=None)

    def test_unsupported_format(self, tmp_path: Path) -> None:
        p = tmp_path / "test.xml"
        p.write_text("<data/>")
        with pytest.raises(ParseError, match="Unsupported"):
            parse_file(p)
