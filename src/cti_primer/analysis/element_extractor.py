"""Extract threat-relevant business elements from BusinessContext.

Pure function — no external dependencies or side effects.
"""

from __future__ import annotations

import json
from pathlib import Path

from cti_primer.models import BusinessContext, BusinessElement

_SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "schema"

# Business trigger keywords (loaded once)
_TRIGGER_KEYWORDS: dict[str, list[str]] | None = None

# OT-related keywords for trigger detection
_OT_KEYWORDS = frozenset(
    {
        "ot",
        "ics",
        "scada",
        "plc",
        "dcs",
        "operational technology",
        "factory",
        "plant",
        "manufacturing floor",
        "industrial control",
    }
)

_CLOUD_KEYWORDS = frozenset(
    {
        "cloud",
        "migration",
        "gcp",
        "aws",
        "azure",
        "kubernetes",
        "クラウド",
        "移行",
    }
)

_IPO_KEYWORDS = frozenset(
    {
        "ipo",
        "listing",
        "上場",
        "public offering",
        "stock exchange",
    }
)


def _load_trigger_keywords() -> dict[str, list[str]]:
    global _TRIGGER_KEYWORDS
    if _TRIGGER_KEYWORDS is None:
        path = _SCHEMA_DIR / "trigger_keywords.json"
        if path.is_file():
            _TRIGGER_KEYWORDS = json.loads(path.read_text(encoding="utf-8"))
        else:
            _TRIGGER_KEYWORDS = {}
    return _TRIGGER_KEYWORDS


def extract_elements(context: BusinessContext) -> list[BusinessElement]:
    """Flatten BusinessContext into categorized elements.

    Returns deduplicated list of BusinessElements covering:
      - industry and geography
      - regulatory context
      - crown jewels and critical assets
      - projects and their data types
      - detected business triggers
    """
    elements: list[BusinessElement] = []
    seen: set[tuple[str, str]] = set()

    def _add(category: str, value: str, source: str) -> None:
        key = (category, value.lower())
        if key not in seen:
            seen.add(key)
            elements.append(
                BusinessElement(
                    category=category,
                    value=value,
                    source_field=source,
                )
            )

    org = context.organization

    # Industry
    _add("industry", org.industry, "organization.industry")

    # Geography
    for geo in org.geography:
        _add("geography", geo, "organization.geography")

    # Regulatory
    for reg in org.regulatory_context:
        _add("regulatory", reg, "organization.regulatory_context")

    # Crown jewels
    for cj in context.crown_jewels:
        _add("asset", cj.name, "crown_jewels")

    # Critical assets
    for ca in context.critical_assets:
        label = ca.hostname or ca.asset_id or ca.asset_type
        if label:
            _add("asset", label, "critical_assets")

    # Projects — data types
    for proj in context.projects:
        for dt in proj.data_types:
            _add("asset", dt, f"projects.{proj.name}.data_types")

    # Triggers
    for trigger in detect_triggers(context):
        _add("trigger", trigger, "detected_trigger")

    return elements


def detect_triggers(context: BusinessContext) -> list[str]:
    """Identify business trigger keywords from context fields.

    Detects:
      - OT connectivity
      - Cloud migration
      - M&A activity
      - IPO / public listing
      - Supply chain expansion
    """
    triggers: list[str] = []
    text_pool = _build_text_pool(context)
    text_lower = text_pool.lower()

    # OT connectivity
    if _any_match(text_lower, _OT_KEYWORDS):
        triggers.append("ot_connectivity")
    for sc in context.supply_chain:
        if sc.has_ot_connectivity:
            if "ot_connectivity" not in triggers:
                triggers.append("ot_connectivity")
            break

    # Cloud migration
    if _any_match(text_lower, _CLOUD_KEYWORDS):
        triggers.append("cloud_migration")

    # M&A
    kw_data = _load_trigger_keywords()
    ma_keywords = [k.lower() for k in kw_data.get("ma_keywords", [])]
    if any(kw in text_lower for kw in ma_keywords):
        triggers.append("ma_activity")

    # IPO
    if context.organization.is_publicly_listed:
        triggers.append("publicly_listed")
    elif _any_match(text_lower, _IPO_KEYWORDS):
        triggers.append("ipo_planned")

    # Supply chain expansion
    expansion_kw = [k.lower() for k in kw_data.get("expansion_keywords", [])]
    if any(kw in text_lower for kw in expansion_kw):
        triggers.append("supply_chain_expansion")

    return triggers


def _build_text_pool(context: BusinessContext) -> str:
    """Concatenate all text fields for keyword detection."""
    parts: list[str] = []

    for obj in context.strategic_objectives:
        parts.append(obj.description)
        parts.extend(obj.key_decisions)

    for proj in context.projects:
        parts.append(proj.name)
        parts.append(proj.description)

    for cj in context.crown_jewels:
        parts.append(cj.name)
        parts.append(cj.description)

    for ca in context.critical_assets:
        parts.append(ca.hostname)
        parts.append(ca.network_zone)
        parts.append(ca.asset_type)

    for sc in context.supply_chain:
        parts.append(sc.name)
        parts.append(sc.category)

    return " ".join(p for p in parts if p)


def _any_match(text: str, keywords: frozenset[str]) -> bool:
    return any(kw in text for kw in keywords)
