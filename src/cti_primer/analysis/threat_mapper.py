"""Map industry and geography to threat profiles via taxonomy lookup.

Uses dictionary-based matching with optional LLM fallback.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cti_primer.llm.client import LLMClient
from cti_primer.llm.prompts import build_guarded_prompt
from cti_primer.models import ThreatProfile

_SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "schema"

_taxonomy_cache: dict[str, Any] | None = None

# Geography normalization: ISO codes to region names used in taxonomy
_GEO_NORMALIZE: dict[str, list[str]] = {
    "JP": ["Japan", "Southeast Asia"],
    "US": ["USA", "North America"],
    "CN": ["China"],
    "TW": ["Taiwan"],
    "KR": ["South Korea", "Southeast Asia"],
    "DE": ["Europe", "Western Europe"],
    "GB": ["Europe", "Western Europe"],
    "FR": ["Europe", "Western Europe"],
    "AU": ["Australia"],
    "IN": ["India"],
    "SG": ["Southeast Asia"],
    "IL": ["Middle East"],
    "SA": ["Middle East"],
    "AE": ["Middle East"],
    "BR": ["South America"],
}


def _load_taxonomy() -> dict[str, Any]:
    global _taxonomy_cache
    if _taxonomy_cache is None:
        path = _SCHEMA_DIR / "threat_taxonomy.json"
        _taxonomy_cache = json.loads(path.read_text(encoding="utf-8"))
    return _taxonomy_cache


def map_threats(
    industry: str,
    geography: list[str],
    triggers: list[str],
    *,
    llm: LLMClient | None = None,
) -> list[ThreatProfile]:
    """Map industry × geography to threat profiles.

    1. Dictionary lookup in threat_taxonomy.json (always runs)
    2. LLM-assisted tag completion (if llm provided and dictionary has gaps)

    Args:
        industry: Organization industry (e.g. "manufacturing").
        geography: List of ISO 3166-1 alpha-2 country codes.
        triggers: Detected business triggers.
        llm: Optional LLM client for enrichment.

    Returns:
        List of matched ThreatProfiles.
    """
    taxonomy = _load_taxonomy()
    profiles: list[ThreatProfile] = []

    # Normalize geography codes to region names
    geo_regions: set[str] = set()
    for code in geography:
        regions = _GEO_NORMALIZE.get(code.upper(), [])
        geo_regions.update(regions)

    # Search actor categories
    actor_cats = taxonomy.get("actor_categories", {})

    for category_name, category_data in actor_cats.items():
        if isinstance(category_data, dict):
            for actor_name, actor_info in category_data.items():
                if not isinstance(actor_info, dict):
                    continue
                profile = _match_actor(
                    actor_name,
                    actor_info,
                    industry,
                    geo_regions,
                    category_name,
                )
                if profile is not None:
                    profiles.append(profile)

    # Check industry threat map
    industry_map = taxonomy.get("industry_threat_map", {})
    industry_lower = industry.lower()
    if industry_lower in industry_map:
        industry_threats = industry_map[industry_lower]
        if isinstance(industry_threats, dict):
            extra_tags = industry_threats.get("additional_tags", [])
            if extra_tags and profiles:
                profiles[0].actor_tags.extend(t for t in extra_tags if t not in profiles[0].actor_tags)

    # Apply trigger-based enrichment
    trigger_map = taxonomy.get("business_trigger_map", {})
    for trigger in triggers:
        if trigger in trigger_map:
            trigger_info = trigger_map[trigger]
            if isinstance(trigger_info, dict):
                extra_tags = trigger_info.get("tags", [])
                if extra_tags and profiles:
                    profiles[0].actor_tags.extend(t for t in extra_tags if t not in profiles[0].actor_tags)

    # LLM fallback if no dictionary matches
    if not profiles and llm is not None:
        profiles = _llm_threat_lookup(industry, geography, llm)

    return profiles


def _match_actor(
    actor_name: str,
    actor_info: dict[str, Any],
    industry: str,
    geo_regions: set[str],
    category: str,
) -> ThreatProfile | None:
    """Check if an actor targets the given industry and geography."""
    target_industries = [i.lower() for i in actor_info.get("target_industries", [])]
    target_geos = actor_info.get("target_geographies", [])

    industry_match = industry.lower() in target_industries
    geo_match = bool(geo_regions & set(target_geos))

    if not (industry_match or geo_match):
        return None

    # Build threat family from category
    family = category
    if category == "state_sponsored":
        family = f"state_sponsored_{actor_name.lower()}"

    return ThreatProfile(
        actor_tags=list(actor_info.get("tags", [])),
        ttps=list(actor_info.get("priority_ttps", [])),
        notable_groups=list(actor_info.get("mitre_groups", [])),
        matched_categories=[category],
        threat_family=family,
    )


def _llm_threat_lookup(
    industry: str,
    geography: list[str],
    llm: LLMClient,
) -> list[ThreatProfile]:
    """Use LLM to suggest threat actor tags when dictionary has no match."""
    data = json.dumps({"industry": industry, "geography": geography})
    system, user = build_guarded_prompt(
        "threat_tag_completion",
        data,
        tag_prefix="org_context",
    )
    try:
        result = llm.complete_json(system, user)
        tags = result.get("tags", [])
        if tags:
            return [
                ThreatProfile(
                    actor_tags=tags,
                    matched_categories=["llm_suggested"],
                    threat_family="general",
                )
            ]
    except Exception:
        pass
    return []
