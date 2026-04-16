"""Tests for cti_primer.models."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from cti_primer.models import (
    AssetTag,
    BusinessContext,
    Organization,
    PIRItem,
    PIROutput,
    RiskScore,
    ThreatCluster,
    ThreatProfile,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _minimal_context() -> BusinessContext:
    return BusinessContext(
        organization=Organization(
            name="Acme Corp",
            industry="manufacturing",
            geography=["JP", "US"],
        ),
    )


def _full_context() -> dict:
    return {
        "organization": {
            "name": "Acme Corp",
            "industry": "manufacturing",
            "geography": ["JP"],
            "employee_range": "1000-5000",
            "is_publicly_listed": True,
        },
        "strategic_objectives": [{"description": "Expand cloud adoption", "sensitivity": "high"}],
        "projects": [
            {
                "name": "Cloud Migration",
                "status": "in_progress",
                "cloud_providers": ["GCP"],
                "data_types": ["financial", "pii"],
            }
        ],
        "crown_jewels": [{"name": "Customer DB", "business_impact": "critical", "exposure": "internal"}],
        "critical_assets": [{"asset_id": "asset-001", "hostname": "db-primary", "network_zone": "internal"}],
        "supply_chain": [{"name": "SAP", "category": "erp", "has_ot_connectivity": False}],
        "recent_incidents": [{"year": 2025, "incident_type": "phishing", "impact": "low"}],
    }


# ---------------------------------------------------------------------------
# BusinessContext tests
# ---------------------------------------------------------------------------


class TestBusinessContext:
    def test_minimal(self) -> None:
        ctx = _minimal_context()
        assert ctx.organization.name == "Acme Corp"
        assert ctx.projects == []

    def test_full_roundtrip(self) -> None:
        data = _full_context()
        ctx = BusinessContext(**data)
        dumped = json.loads(ctx.model_dump_json())
        ctx2 = BusinessContext(**dumped)
        assert ctx2.organization.name == ctx.organization.name
        assert len(ctx2.crown_jewels) == 1

    def test_missing_organization_fails(self) -> None:
        with pytest.raises(ValidationError):
            BusinessContext()  # type: ignore[call-arg]


# ---------------------------------------------------------------------------
# Analysis model tests
# ---------------------------------------------------------------------------


class TestAssetTag:
    def test_valid_range(self) -> None:
        tag = AssetTag(tag="erp", confidence=0.85, source="keyword")
        assert tag.confidence == 0.85

    def test_out_of_range_fails(self) -> None:
        with pytest.raises(ValidationError):
            AssetTag(tag="erp", confidence=1.5, source="keyword")

    def test_zero_confidence(self) -> None:
        tag = AssetTag(tag="cloud", confidence=0.0, source="data_type")
        assert tag.confidence == 0.0


class TestRiskScore:
    def test_valid(self) -> None:
        score = RiskScore(
            likelihood=4,
            impact=3,
            composite=12.0,
            intelligence_level="operational",
        )
        assert score.composite == 12.0

    def test_likelihood_out_of_range(self) -> None:
        with pytest.raises(ValidationError):
            RiskScore(likelihood=0, impact=3, composite=0, intelligence_level="tactical")

    def test_likelihood_max(self) -> None:
        with pytest.raises(ValidationError):
            RiskScore(likelihood=6, impact=3, composite=0, intelligence_level="tactical")


class TestThreatProfile:
    def test_defaults(self) -> None:
        tp = ThreatProfile()
        assert tp.actor_tags == []
        assert tp.threat_family == ""


class TestThreatCluster:
    def test_cluster(self) -> None:
        cluster = ThreatCluster(
            family="ransomware",
            asset_tags=["erp", "database"],
            aggregate_score=18.0,
        )
        assert cluster.family == "ransomware"


# ---------------------------------------------------------------------------
# Output model tests
# ---------------------------------------------------------------------------


class TestPIROutput:
    def test_generated_at_auto(self) -> None:
        pir = PIROutput(organization="Acme Corp")
        assert pir.generated_at != ""
        assert "T" in pir.generated_at

    def test_with_items(self) -> None:
        item = PIRItem(
            pir_id="PIR-001",
            intelligence_level="strategic",
            description="What nation-state actors target manufacturing?",
            threat_actor_tags=["china-nexus"],
            valid_from="2026-04-16T00:00:00Z",
            valid_until="2027-04-16T00:00:00Z",
        )
        pir = PIROutput(organization="Acme Corp", pir_items=[item])
        assert len(pir.pir_items) == 1
        assert pir.pir_items[0].pir_id == "PIR-001"

    def test_json_roundtrip(self) -> None:
        pir = PIROutput(
            organization="Test",
            pir_items=[
                PIRItem(
                    pir_id="PIR-001",
                    intelligence_level="tactical",
                    description="Test PIR",
                    risk_score=RiskScore(
                        likelihood=3,
                        impact=4,
                        composite=12.0,
                        intelligence_level="tactical",
                    ),
                )
            ],
        )
        json_str = pir.model_dump_json()
        pir2 = PIROutput.model_validate_json(json_str)
        assert pir2.pir_items[0].risk_score is not None
        assert pir2.pir_items[0].risk_score.composite == 12.0
