"""Data models for cti-primer.

Covers three layers:
  1. Input  — BusinessContext (user-supplied organizational data)
  2. Analysis — intermediate results from the 5-step pipeline
  3. Output — SAGE-compatible PIR JSON
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# 1. Input models
# ---------------------------------------------------------------------------


class Organization(BaseModel):
    """Organization profile."""

    name: str
    industry: str
    geography: list[str] = Field(default_factory=list)
    employee_range: str = ""
    revenue_range: str = ""
    regulatory_context: list[str] = Field(default_factory=list)
    is_publicly_listed: bool = False


class StrategicObjective(BaseModel):
    """Business strategic objective."""

    description: str
    sensitivity: str = "medium"  # low | medium | high | critical
    timeline: str = ""
    key_decisions: list[str] = Field(default_factory=list)


class Project(BaseModel):
    """Business project or initiative."""

    name: str
    description: str = ""
    status: str = "in_progress"  # planned | in_progress | completed | cancelled
    vendors: list[str] = Field(default_factory=list)
    cloud_providers: list[str] = Field(default_factory=list)
    data_types: list[str] = Field(default_factory=list)


class CrownJewel(BaseModel):
    """High-value organizational asset."""

    name: str
    description: str = ""
    business_impact: str = "high"  # low | medium | high | critical
    exposure: str = "internal"  # internal | partner | external


class CriticalAsset(BaseModel):
    """Technical infrastructure asset."""

    asset_id: str = ""
    hostname: str = ""
    os: str = ""
    network_zone: str = ""
    asset_type: str = ""
    dependencies: list[str] = Field(default_factory=list)
    vendor_roles: list[str] = Field(default_factory=list)
    criticality: str = "high"  # low | medium | high | critical


class SupplyChainEntry(BaseModel):
    """Supply chain vendor or provider."""

    name: str
    category: str = ""  # erp | msp | software | hardware | cloud | financial
    has_ot_connectivity: bool = False


class RecentIncident(BaseModel):
    """Past security incident."""

    year: int
    incident_type: str
    impact: str = ""
    description: str = ""


class BusinessContext(BaseModel):
    """Complete business context input for PIR generation.

    This is the primary input schema — users provide this as JSON or
    via LLM-structured Markdown.
    """

    organization: Organization
    strategic_objectives: list[StrategicObjective] = Field(default_factory=list)
    projects: list[Project] = Field(default_factory=list)
    crown_jewels: list[CrownJewel] = Field(default_factory=list)
    critical_assets: list[CriticalAsset] = Field(default_factory=list)
    supply_chain: list[SupplyChainEntry] = Field(default_factory=list)
    recent_incidents: list[RecentIncident] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# 2. Analysis intermediate models
# ---------------------------------------------------------------------------


class BusinessElement(BaseModel):
    """Flattened element extracted from BusinessContext."""

    category: str  # asset | trigger | regulatory | geography | industry
    value: str
    source_field: str


class AssetTag(BaseModel):
    """Mapped SAGE asset tag."""

    tag: str
    confidence: float = Field(ge=0.0, le=1.0)
    source: str  # keyword | data_type | cloud | llm


class ThreatProfile(BaseModel):
    """Threat actor profile from taxonomy mapping."""

    actor_tags: list[str] = Field(default_factory=list)
    ttps: list[str] = Field(default_factory=list)
    notable_groups: list[str] = Field(default_factory=list)
    matched_categories: list[str] = Field(default_factory=list)
    threat_family: str = ""


class RiskScore(BaseModel):
    """Risk assessment score."""

    likelihood: int = Field(ge=1, le=5)
    impact: int = Field(ge=1, le=5)
    composite: float = Field(ge=0.0)
    sage_boosted: bool = False
    intelligence_level: str  # strategic | operational | tactical
    rationale: str = ""


class ThreatCluster(BaseModel):
    """Grouped threats for PIR generation."""

    family: str
    profiles: list[ThreatProfile] = Field(default_factory=list)
    asset_tags: list[str] = Field(default_factory=list)
    aggregate_score: float = 0.0


# ---------------------------------------------------------------------------
# 3. Output models (SAGE-compatible PIR)
# ---------------------------------------------------------------------------


class AssetWeightRule(BaseModel):
    """SAGE asset weight rule within a PIR."""

    tag: str
    multiplier: float = 1.0


class PIRItem(BaseModel):
    """Single Priority Intelligence Requirement."""

    pir_id: str
    intelligence_level: str  # strategic | operational | tactical
    description: str
    rationale: str = ""
    collection_focus: list[str] = Field(default_factory=list)
    recommended_action: str = ""
    threat_actor_tags: list[str] = Field(default_factory=list)
    asset_weight_rules: list[AssetWeightRule] = Field(default_factory=list)
    valid_from: str = ""  # ISO 8601
    valid_until: str = ""  # ISO 8601
    risk_score: RiskScore | None = None


class PIROutput(BaseModel):
    """Complete PIR generation output — SAGE-compatible."""

    organization: str
    generated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    pir_items: list[PIRItem] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
