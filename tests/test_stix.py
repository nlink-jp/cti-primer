"""Tests for cti_primer.ingest.report_reader and stix_extractor."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from cti_primer.ingest.report_reader import (
    _truncate,
    read_file,
    read_source,
)
from cti_primer.ingest.stix_extractor import (
    StixExtractionError,
    _validate_objects,
    build_stix_bundle,
    extract_stix,
)

FIXTURES = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Report Reader
# ---------------------------------------------------------------------------


class TestReportReader:
    def test_read_markdown_file(self) -> None:
        text = read_file(FIXTURES / "sample_report.md")
        assert "APT41" in text
        assert "CVE-2025-12345" in text

    def test_read_text_file(self, tmp_path: Path) -> None:
        p = tmp_path / "report.txt"
        p.write_text("Test report content")
        text = read_file(p)
        assert text == "Test report content"

    def test_truncate(self) -> None:
        long_text = "a" * 50_000
        result = _truncate(long_text, max_chars=1000)
        assert len(result) == 1000

    def test_truncate_short_text(self) -> None:
        short = "hello"
        assert _truncate(short) == "hello"

    def test_read_source_file(self) -> None:
        text = read_source(str(FIXTURES / "sample_report.md"))
        assert "APT41" in text

    def test_read_html_file(self, tmp_path: Path) -> None:
        p = tmp_path / "report.html"
        p.write_text("<html><body><p>Test report</p><script>bad</script></body></html>")
        text = read_file(p)
        assert "Test report" in text
        assert "bad" not in text  # script removed


# ---------------------------------------------------------------------------
# STIX Extractor
# ---------------------------------------------------------------------------


class StubLLM:
    def __init__(self, response: Any) -> None:
        self._response = response

    def complete(self, system: str, user: str) -> str:
        return json.dumps(self._response)

    def complete_json(self, system: str, user: str) -> Any:
        return self._response


class TestStixExtractor:
    def test_extract_stix_basic(self) -> None:
        llm = StubLLM(
            [
                {
                    "type": "threat-actor",
                    "name": "APT41",
                    "threat_actor_types": ["nation-state"],
                },
                {
                    "type": "malware",
                    "name": "ShadowPad Lite",
                    "malware_types": ["backdoor"],
                },
            ]
        )
        bundle = extract_stix("Some report text", llm)
        assert bundle["type"] == "bundle"
        assert bundle["spec_version"] == "2.1"
        assert len(bundle["objects"]) == 2
        assert bundle["objects"][0]["name"] == "APT41"

    def test_adds_missing_fields(self) -> None:
        llm = StubLLM(
            [
                {"type": "threat-actor", "name": "Test Actor"},
            ]
        )
        bundle = extract_stix("report", llm)
        obj = bundle["objects"][0]
        assert "id" in obj
        assert obj["id"].startswith("threat-actor--")
        assert "created" in obj
        assert "spec_version" in obj

    def test_filters_invalid_types(self) -> None:
        llm = StubLLM(
            [
                {"type": "threat-actor", "name": "Valid"},
                {"type": "invalid-type", "name": "Invalid"},
            ]
        )
        bundle = extract_stix("report", llm)
        assert len(bundle["objects"]) == 1

    def test_filters_objects_without_name(self) -> None:
        llm = StubLLM(
            [
                {"type": "threat-actor", "name": "Valid"},
                {"type": "malware"},  # no name
            ]
        )
        bundle = extract_stix("report", llm)
        assert len(bundle["objects"]) == 1

    def test_relationship_without_name_ok(self) -> None:
        llm = StubLLM(
            [
                {
                    "type": "relationship",
                    "relationship_type": "uses",
                    "source_ref": "threat-actor--1",
                    "target_ref": "malware--2",
                },
            ]
        )
        bundle = extract_stix("report", llm)
        assert len(bundle["objects"]) == 1
        assert bundle["objects"][0]["type"] == "relationship"

    def test_llm_failure(self) -> None:
        class FailLLM:
            def complete(self, s: str, u: str) -> str:
                raise Exception("fail")

            def complete_json(self, s: str, u: str) -> Any:
                raise Exception("fail")

        with pytest.raises(StixExtractionError):
            extract_stix("report", FailLLM())


class TestBuildStixBundle:
    def test_bundle_structure(self) -> None:
        bundle = build_stix_bundle([{"type": "threat-actor", "name": "Test"}])
        assert bundle["type"] == "bundle"
        assert bundle["id"].startswith("bundle--")
        assert bundle["spec_version"] == "2.1"
        assert len(bundle["objects"]) == 1

    def test_empty_bundle(self) -> None:
        bundle = build_stix_bundle([])
        assert bundle["objects"] == []


class TestValidateObjects:
    def test_valid_objects(self) -> None:
        raw = [
            {"type": "threat-actor", "name": "APT1"},
            {"type": "malware", "name": "RAT"},
        ]
        result = _validate_objects(raw)
        assert len(result) == 2

    def test_non_dict_skipped(self) -> None:
        result = _validate_objects(["not a dict", 42])
        assert result == []

    def test_invalid_type_skipped(self) -> None:
        result = _validate_objects([{"type": "bad-type", "name": "test"}])
        assert result == []
