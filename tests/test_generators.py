"""Tests for cti_primer.generator modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cti_primer.models import (
    AssetTag,
    BusinessContext,
    CriticalAsset,
    Organization,
    PIRItem,
    PIROutput,
    RiskScore,
    ThreatCluster,
    ThreatProfile,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_context() -> BusinessContext:
    raw = (FIXTURES / "sample_context.json").read_text()
    return BusinessContext(**json.loads(raw))


class StubLLM:
    def __init__(self, response: Any = None) -> None:
        self._response = response or {}

    def complete(self, system: str, user: str) -> str:
        return json.dumps(self._response)

    def complete_json(self, system: str, user: str) -> Any:
        return self._response


# ===========================================================================
# PIR Builder
# ===========================================================================


class TestPIRBuilder:
    def test_builds_pirs_above_threshold(self) -> None:
        from cti_primer.generator.pir_builder import build_pirs

        ctx = _load_context()
        clusters = [
            ThreatCluster(
                family="state_sponsored",
                profiles=[
                    ThreatProfile(
                        actor_tags=["apt-china"],
                        notable_groups=["APT41", "menuPass"],
                        matched_categories=["state_sponsored"],
                    )
                ],
                asset_tags=["erp", "ot"],
                aggregate_score=20.0,
            ),
        ]
        scores = [
            RiskScore(
                likelihood=4,
                impact=5,
                composite=20.0,
                intelligence_level="strategic",
            )
        ]
        assets = [AssetTag(tag="erp", confidence=0.9, source="keyword")]

        result = build_pirs(ctx, clusters, scores, assets)
        assert result.organization == "Acme Manufacturing Co."
        assert len(result.pir_items) == 1
        assert result.pir_items[0].pir_id == "PIR-001"
        assert result.pir_items[0].intelligence_level == "strategic"

    def test_filters_below_threshold(self) -> None:
        from cti_primer.generator.pir_builder import build_pirs

        ctx = _load_context()
        clusters = [
            ThreatCluster(
                family="hacktivism",
                profiles=[ThreatProfile(matched_categories=["hacktivism"])],
                asset_tags=["web"],
                aggregate_score=6.0,
            ),
        ]
        scores = [
            RiskScore(
                likelihood=2,
                impact=3,
                composite=6.0,
                intelligence_level="tactical",
            )
        ]

        result = build_pirs(ctx, clusters, scores, [])
        assert len(result.pir_items) == 0
        assert result.metadata["filtered_below_threshold"] == 1

    def test_description_is_question(self) -> None:
        from cti_primer.generator.pir_builder import build_pirs

        ctx = _load_context()
        clusters = [
            ThreatCluster(
                family="ransomware",
                profiles=[ThreatProfile(matched_categories=["ransomware"])],
                aggregate_score=15.0,
            ),
        ]
        scores = [
            RiskScore(
                likelihood=3,
                impact=5,
                composite=15.0,
                intelligence_level="operational",
            )
        ]

        result = build_pirs(ctx, clusters, scores, [])
        assert len(result.pir_items) == 1
        assert result.pir_items[0].description.endswith("?")

    def test_validity_window_strategic(self) -> None:
        from cti_primer.generator.pir_builder import build_pirs

        ctx = _load_context()
        clusters = [
            ThreatCluster(
                family="state_sponsored",
                profiles=[ThreatProfile(matched_categories=["state_sponsored"])],
                aggregate_score=25.0,
            ),
        ]
        scores = [
            RiskScore(
                likelihood=5,
                impact=5,
                composite=25.0,
                intelligence_level="strategic",
            )
        ]

        result = build_pirs(ctx, clusters, scores, [])
        item = result.pir_items[0]
        assert item.valid_from != ""
        assert item.valid_until != ""

    def test_with_llm(self) -> None:
        from cti_primer.generator.pir_builder import build_pirs

        llm = StubLLM(
            {
                "description": "What APT groups target manufacturing in APAC?",
                "rationale": "High value IP assets",
                "collection_focus": ["Monitor dark web", "Track APT41"],
                "recommended_action": "Increase SOC coverage",
            }
        )
        ctx = _load_context()
        clusters = [
            ThreatCluster(
                family="state_sponsored",
                profiles=[ThreatProfile(matched_categories=["state_sponsored"])],
                aggregate_score=20.0,
            ),
        ]
        scores = [
            RiskScore(
                likelihood=4,
                impact=5,
                composite=20.0,
                intelligence_level="strategic",
            )
        ]

        result = build_pirs(ctx, clusters, scores, [], llm=llm)
        assert result.pir_items[0].description == "What APT groups target manufacturing in APAC?"

    def test_empty_clusters(self) -> None:
        from cti_primer.generator.pir_builder import build_pirs

        ctx = _load_context()
        result = build_pirs(ctx, [], [], [])
        assert len(result.pir_items) == 0


# ===========================================================================
# Report Builder
# ===========================================================================


class TestReportBuilder:
    def test_generates_markdown(self) -> None:
        from cti_primer.generator.report_builder import build_report

        ctx = _load_context()
        pir = PIROutput(
            organization="Acme",
            pir_items=[
                PIRItem(
                    pir_id="PIR-001",
                    intelligence_level="strategic",
                    description="What threats target manufacturing?",
                    collection_focus=["Monitor feeds"],
                ),
            ],
        )
        clusters = [ThreatCluster(family="state_sponsored", aggregate_score=20.0)]
        scores = [RiskScore(likelihood=4, impact=5, composite=20, intelligence_level="strategic")]

        report = build_report(ctx, pir, clusters, scores)
        assert "# Collection Plan" in report
        assert "PIR-001" in report
        assert "manufacturing" in report.lower()

    def test_no_pirs_shows_monitoring(self) -> None:
        from cti_primer.generator.report_builder import build_report

        ctx = _load_context()
        pir = PIROutput(organization="Acme")
        report = build_report(ctx, pir, [], [])
        assert "Monitoring Status" in report

    def test_write_report(self, tmp_path: Path) -> None:
        from cti_primer.generator.report_builder import write_report

        out = tmp_path / "sub" / "report.md"
        write_report("# Test\nContent", out)
        assert out.read_text() == "# Test\nContent"


# ===========================================================================
# Assets Generator
# ===========================================================================


class TestAssetsGenerator:
    def test_generates_assets(self) -> None:
        from cti_primer.generator.assets_generator import generate_assets

        ctx = _load_context()
        result = generate_assets(ctx)
        assert result["organization"] == "Acme Manufacturing Co."
        assert len(result["assets"]) == 3
        assert len(result["network_segments"]) >= 1

    def test_asset_id_normalization(self) -> None:
        from cti_primer.generator.assets_generator import generate_assets

        ctx = BusinessContext(
            organization=Organization(name="Test", industry="tech"),
            critical_assets=[
                CriticalAsset(
                    asset_id="my-server",
                    hostname="srv1",
                    network_zone="internal",
                    criticality="high",
                ),
            ],
        )
        result = generate_assets(ctx)
        assert result["assets"][0]["asset_id"] == "asset-my-server"

    def test_internet_facing_detection(self) -> None:
        from cti_primer.generator.assets_generator import generate_assets

        ctx = BusinessContext(
            organization=Organization(name="Test", industry="tech"),
            critical_assets=[
                CriticalAsset(
                    asset_id="asset-web-001",
                    hostname="web-prod",
                    network_zone="dmz",
                ),
            ],
        )
        result = generate_assets(ctx)
        assert result["assets"][0]["is_internet_facing"] is True
        assert "external-facing" in result["assets"][0]["tags"]

    def test_connections_from_dependencies(self) -> None:
        from cti_primer.generator.assets_generator import generate_assets

        ctx = _load_context()
        result = generate_assets(ctx)
        conns = result["connections"]
        assert len(conns) >= 1
        assert any(c["from_asset"] == "asset-erp-001" and c["to_asset"] == "asset-db-001" for c in conns)

    def test_empty_assets(self) -> None:
        from cti_primer.generator.assets_generator import generate_assets

        ctx = BusinessContext(
            organization=Organization(name="Test", industry="tech"),
        )
        result = generate_assets(ctx)
        assert result["assets"] == []
        assert result["network_segments"] == []
        assert result["connections"] == []
