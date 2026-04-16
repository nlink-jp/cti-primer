"""Tests for cti_primer.analysis modules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cti_primer.models import (
    AssetTag,
    BusinessContext,
    BusinessElement,
    Organization,
    Project,
    RiskScore,
    SupplyChainEntry,
    ThreatProfile,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _load_context() -> BusinessContext:
    raw = (FIXTURES / "sample_context.json").read_text()
    return BusinessContext(**json.loads(raw))


# ---------------------------------------------------------------------------
# StubLLM for optional LLM tests
# ---------------------------------------------------------------------------


class StubLLM:
    def __init__(self, response: Any = None) -> None:
        self._response = response or {}
        self.calls: list[tuple[str, str]] = []

    def complete(self, system: str, user: str) -> str:
        self.calls.append((system, user))
        return json.dumps(self._response)

    def complete_json(self, system: str, user: str) -> Any:
        self.calls.append((system, user))
        return self._response


# ===========================================================================
# Element Extractor
# ===========================================================================


class TestElementExtractor:
    def test_extracts_industry(self) -> None:
        from cti_primer.analysis.element_extractor import extract_elements

        ctx = _load_context()
        elements = extract_elements(ctx)
        industries = [e for e in elements if e.category == "industry"]
        assert len(industries) == 1
        assert industries[0].value == "manufacturing"

    def test_extracts_geography(self) -> None:
        from cti_primer.analysis.element_extractor import extract_elements

        ctx = _load_context()
        elements = extract_elements(ctx)
        geos = [e for e in elements if e.category == "geography"]
        assert {e.value for e in geos} == {"JP", "US", "CN"}

    def test_extracts_crown_jewels(self) -> None:
        from cti_primer.analysis.element_extractor import extract_elements

        ctx = _load_context()
        elements = extract_elements(ctx)
        assets = [e for e in elements if e.category == "asset"]
        asset_values = {e.value for e in assets}
        assert "Product Design Database" in asset_values
        assert "Customer PII Database" in asset_values

    def test_deduplicates(self) -> None:
        from cti_primer.analysis.element_extractor import extract_elements

        ctx = _load_context()
        elements = extract_elements(ctx)
        keys = [(e.category, e.value.lower()) for e in elements]
        assert len(keys) == len(set(keys))

    def test_detects_ot_trigger(self) -> None:
        from cti_primer.analysis.element_extractor import detect_triggers

        ctx = _load_context()
        triggers = detect_triggers(ctx)
        assert "ot_connectivity" in triggers

    def test_detects_cloud_migration(self) -> None:
        from cti_primer.analysis.element_extractor import detect_triggers

        ctx = _load_context()
        triggers = detect_triggers(ctx)
        assert "cloud_migration" in triggers

    def test_detects_publicly_listed(self) -> None:
        from cti_primer.analysis.element_extractor import detect_triggers

        ctx = _load_context()
        triggers = detect_triggers(ctx)
        assert "publicly_listed" in triggers

    def test_minimal_context_no_triggers(self) -> None:
        from cti_primer.analysis.element_extractor import detect_triggers

        ctx = BusinessContext(
            organization=Organization(name="Test", industry="finance"),
        )
        triggers = detect_triggers(ctx)
        assert triggers == []


# ===========================================================================
# Asset Mapper
# ===========================================================================


class TestAssetMapper:
    def test_keyword_matching(self) -> None:
        from cti_primer.analysis.asset_mapper import map_assets
        from cti_primer.analysis.element_extractor import extract_elements

        ctx = _load_context()
        elements = extract_elements(ctx)
        tags = map_assets(elements, ctx)
        tag_names = {t.tag for t in tags}
        # SAP -> erp, SCADA -> ot, cloud -> cloud
        assert "erp" in tag_names
        assert "ot" in tag_names
        assert "cloud" in tag_names

    def test_data_type_mapping(self) -> None:
        from cti_primer.analysis.asset_mapper import map_assets

        ctx = BusinessContext(
            organization=Organization(name="Test", industry="tech"),
            projects=[
                Project(
                    name="P1",
                    data_types=["financial", "source_code"],
                    cloud_providers=["GCP"],
                ),
            ],
        )
        elements = [
            BusinessElement(category="asset", value="financial", source_field="projects.P1.data_types"),
            BusinessElement(category="asset", value="source_code", source_field="projects.P1.data_types"),
        ]
        tags = map_assets(elements, ctx)
        tag_names = {t.tag for t in tags}
        assert "cloud" in tag_names  # GCP cloud provider

    def test_ot_connectivity_from_supply_chain(self) -> None:
        from cti_primer.analysis.asset_mapper import map_assets

        ctx = BusinessContext(
            organization=Organization(name="Test", industry="mfg"),
            supply_chain=[
                SupplyChainEntry(name="Vendor", category="software", has_ot_connectivity=True),
            ],
        )
        tags = map_assets([], ctx)
        assert any(t.tag == "ot" for t in tags)

    def test_sorted_by_confidence(self) -> None:
        from cti_primer.analysis.asset_mapper import map_assets
        from cti_primer.analysis.element_extractor import extract_elements

        ctx = _load_context()
        elements = extract_elements(ctx)
        tags = map_assets(elements, ctx)
        for i in range(len(tags) - 1):
            assert tags[i].confidence >= tags[i + 1].confidence

    def test_llm_enrichment(self) -> None:
        from cti_primer.analysis.asset_mapper import map_assets

        llm = StubLLM(
            [
                {"tag": "siem", "confidence": 0.7, "reason": "monitoring mentioned"},
            ]
        )
        ctx = BusinessContext(
            organization=Organization(name="Test", industry="tech"),
        )
        tags = map_assets([], ctx, llm=llm)
        assert any(t.tag == "siem" for t in tags)


# ===========================================================================
# Threat Mapper
# ===========================================================================


class TestThreatMapper:
    def test_manufacturing_jp_matches(self) -> None:
        from cti_primer.analysis.threat_mapper import map_threats

        profiles = map_threats("manufacturing", ["JP", "US"], [])
        assert len(profiles) > 0
        # China targets manufacturing + Japan
        all_tags = set()
        for p in profiles:
            all_tags.update(p.actor_tags)
        assert "apt-china" in all_tags or "espionage" in all_tags

    def test_notable_groups_populated(self) -> None:
        from cti_primer.analysis.threat_mapper import map_threats

        profiles = map_threats("manufacturing", ["JP"], [])
        has_groups = any(len(p.notable_groups) > 0 for p in profiles)
        assert has_groups

    def test_no_match_returns_empty(self) -> None:
        from cti_primer.analysis.threat_mapper import map_threats

        profiles = map_threats("underwater_basket_weaving", ["ZZ"], [])
        assert profiles == []

    def test_llm_fallback(self) -> None:
        from cti_primer.analysis.threat_mapper import map_threats

        llm = StubLLM({"tags": ["ransomware", "cybercriminal"], "reasoning": "test"})
        profiles = map_threats("underwater_basket_weaving", ["ZZ"], [], llm=llm)
        assert len(profiles) == 1
        assert "ransomware" in profiles[0].actor_tags


# ===========================================================================
# Risk Scorer
# ===========================================================================


class TestRiskScorer:
    def test_basic_scoring(self) -> None:
        from cti_primer.analysis.risk_scorer import score_risks

        ctx = _load_context()
        profiles = [
            ThreatProfile(
                actor_tags=["apt-china", "espionage"],
                matched_categories=["state_sponsored"],
                notable_groups=["APT41", "menuPass", "MirrorFace", "Mustang Panda", "Salt Typhoon"],
                threat_family="state_sponsored",
            )
        ]
        triggers = ["cloud_migration", "ot_connectivity"]
        assets = [AssetTag(tag="erp", confidence=0.9, source="keyword")]

        scores = score_risks(ctx, profiles, assets, triggers)
        assert len(scores) == 1
        assert 1 <= scores[0].likelihood <= 5
        assert 1 <= scores[0].impact <= 5
        assert scores[0].composite > 0

    def test_impact_from_crown_jewels(self) -> None:
        from cti_primer.analysis.risk_scorer import score_risks

        ctx = _load_context()  # has critical crown jewels
        profiles = [ThreatProfile(matched_categories=["test"])]
        scores = score_risks(ctx, profiles, [], [])
        assert scores[0].impact == 5  # critical crown jewels

    def test_sage_boost(self) -> None:
        from cti_primer.analysis.risk_scorer import score_risks

        ctx = BusinessContext(
            organization=Organization(name="Test", industry="tech"),
        )
        profiles = [
            ThreatProfile(
                actor_tags=["apt-china"],
                matched_categories=["state_sponsored"],
            )
        ]
        scores_normal = score_risks(ctx, profiles, [], [])
        scores_boosted = score_risks(
            ctx,
            profiles,
            [],
            [],
            sage_observations={"apt-china": 3},
        )
        assert scores_boosted[0].likelihood >= scores_normal[0].likelihood
        assert scores_boosted[0].sage_boosted is True

    def test_intelligence_level_strategic(self) -> None:
        from cti_primer.analysis.risk_scorer import classify_intelligence_level

        assert classify_intelligence_level(20, []) == "strategic"
        assert classify_intelligence_level(25, []) == "strategic"

    def test_intelligence_level_operational(self) -> None:
        from cti_primer.analysis.risk_scorer import classify_intelligence_level

        assert classify_intelligence_level(15, []) == "operational"
        assert classify_intelligence_level(12, []) == "operational"

    def test_intelligence_level_tactical(self) -> None:
        from cti_primer.analysis.risk_scorer import classify_intelligence_level

        assert classify_intelligence_level(8, []) == "tactical"

    def test_high_risk_trigger_boosts_to_operational(self) -> None:
        from cti_primer.analysis.risk_scorer import classify_intelligence_level

        assert classify_intelligence_level(8, ["ot_connectivity"]) == "operational"

    def test_no_crown_jewels_default_impact(self) -> None:
        from cti_primer.analysis.risk_scorer import score_risks

        ctx = BusinessContext(
            organization=Organization(name="Test", industry="tech"),
        )
        profiles = [ThreatProfile(matched_categories=["test"])]
        scores = score_risks(ctx, profiles, [], [])
        assert scores[0].impact == 2


# ===========================================================================
# PIR Clusterer
# ===========================================================================


class TestPIRClusterer:
    def test_clusters_by_family(self) -> None:
        from cti_primer.analysis.pir_clusterer import cluster_threats

        profiles = [
            ThreatProfile(actor_tags=["apt-china", "espionage"], threat_family="state_sponsored_china"),
            ThreatProfile(actor_tags=["ransomware"], threat_family="ransomware"),
        ]
        scores = [
            RiskScore(likelihood=4, impact=5, composite=20, intelligence_level="strategic"),
            RiskScore(likelihood=3, impact=4, composite=12, intelligence_level="operational"),
        ]
        clusters = cluster_threats(profiles, scores)
        assert len(clusters) == 2
        families = {c.family for c in clusters}
        assert "state_sponsored" in families
        assert "ransomware" in families

    def test_max_clusters_limit(self) -> None:
        from cti_primer.analysis.pir_clusterer import cluster_threats

        profiles = [ThreatProfile(actor_tags=[f"tag-{i}"], threat_family=f"family_{i}") for i in range(10)]
        scores = [RiskScore(likelihood=3, impact=3, composite=9, intelligence_level="tactical") for _ in range(10)]
        clusters = cluster_threats(profiles, scores, max_clusters=3)
        assert len(clusters) <= 3

    def test_sorted_by_score(self) -> None:
        from cti_primer.analysis.pir_clusterer import cluster_threats

        profiles = [
            ThreatProfile(actor_tags=["ransomware"], threat_family="ransomware"),
            ThreatProfile(actor_tags=["apt-china"], threat_family="state_sponsored_china"),
        ]
        scores = [
            RiskScore(likelihood=2, impact=3, composite=6, intelligence_level="tactical"),
            RiskScore(likelihood=5, impact=5, composite=25, intelligence_level="strategic"),
        ]
        clusters = cluster_threats(profiles, scores)
        assert clusters[0].aggregate_score >= clusters[1].aggregate_score

    def test_empty_input(self) -> None:
        from cti_primer.analysis.pir_clusterer import cluster_threats

        assert cluster_threats([], []) == []
