"""Map business elements to SAGE-compatible asset tags.

Uses dictionary-based keyword matching with optional LLM enrichment.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from cti_primer.llm.client import LLMClient
from cti_primer.llm.prompts import build_guarded_prompt
from cti_primer.models import AssetTag, BusinessContext, BusinessElement

_SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "schema"

_asset_tags_cache: dict[str, Any] | None = None


def _load_asset_tags() -> dict[str, Any]:
    global _asset_tags_cache
    if _asset_tags_cache is None:
        path = _SCHEMA_DIR / "asset_tags.json"
        _asset_tags_cache = json.loads(path.read_text(encoding="utf-8"))
    return _asset_tags_cache


def map_assets(
    elements: list[BusinessElement],
    context: BusinessContext,
    *,
    llm: LLMClient | None = None,
) -> list[AssetTag]:
    """Map business elements to SAGE asset tags.

    Three mapping strategies (always applied in order):
      1. Keyword matching against asset_tags.json
      2. Data type mapping
      3. Cloud provider and network zone mapping

    Optional LLM enrichment when llm is provided.

    Returns deduplicated tags sorted by confidence (descending).
    """
    db = _load_asset_tags()
    tags: dict[str, AssetTag] = {}

    def _upsert(tag: str, confidence: float, source: str) -> None:
        if tag in tags:
            if confidence > tags[tag].confidence:
                tags[tag] = AssetTag(tag=tag, confidence=confidence, source=source)
        else:
            tags[tag] = AssetTag(tag=tag, confidence=confidence, source=source)

    # 1. Keyword matching
    asset_type_map = db.get("asset_type_map", {})
    text_pool = " ".join(e.value for e in elements).lower()

    for _type_key, type_info in asset_type_map.items():
        keywords = type_info.get("keywords", [])
        sage_tags = type_info.get("sage_tags", [])
        for kw in keywords:
            if kw.lower() in text_pool:
                for tag in sage_tags:
                    _upsert(tag, 0.85, "keyword")
                break

    # 2. Data type mapping
    data_type_map = db.get("data_type_tag_map", {})
    for elem in elements:
        if elem.source_field.endswith("data_types"):
            mapped_tags = data_type_map.get(elem.value, [])
            for tag in mapped_tags:
                _upsert(tag, 0.9, "data_type")

    # 3. Cloud provider mapping
    cloud_map = db.get("cloud_provider_tag_map", {})
    for proj in context.projects:
        for provider in proj.cloud_providers:
            mapped = cloud_map.get(provider.lower(), cloud_map.get(provider, []))
            for tag in mapped:
                _upsert(tag, 0.9, "cloud")

    # 4. Network zone mapping
    zone_map = db.get("network_zone_tag_map", {})
    for asset in context.critical_assets:
        zone = asset.network_zone.lower()
        if zone in zone_map:
            for tag in zone_map[zone]:
                _upsert(tag, 0.85, "keyword")

    # 5. OT connectivity from supply chain
    for sc in context.supply_chain:
        if sc.has_ot_connectivity:
            _upsert("ot", 0.9, "keyword")

    # 6. Optional LLM enrichment
    if llm is not None:
        _enrich_with_llm(elements, tags, llm, _upsert)

    result = sorted(tags.values(), key=lambda t: t.confidence, reverse=True)
    return result


def _enrich_with_llm(
    elements: list[BusinessElement],
    existing: dict[str, AssetTag],
    llm: LLMClient,
    upsert: Any,
) -> None:
    """Use LLM to discover additional asset tags."""
    elements_text = json.dumps(
        [e.model_dump() for e in elements],
        ensure_ascii=False,
    )
    system, user = build_guarded_prompt(
        "asset_mapping",
        elements_text,
        tag_prefix="elements",
    )
    try:
        result = llm.complete_json(system, user)
        if isinstance(result, list):
            for item in result:
                tag = item.get("tag", "")
                conf = float(item.get("confidence", 0.5))
                if tag and 0.5 <= conf <= 1.0:
                    upsert(tag, conf, "llm")
    except Exception:
        pass  # LLM enrichment is best-effort
