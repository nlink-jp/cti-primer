"""Build SAGE-compatible PIR JSON from analysis results.

Generates PIR items per cluster with validity windows and optional LLM augmentation.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

from cti_primer.llm.client import LLMClient
from cti_primer.llm.prompts import build_guarded_prompt
from cti_primer.models import (
    AssetTag,
    AssetWeightRule,
    BusinessContext,
    PIRItem,
    PIROutput,
    RiskScore,
    ThreatCluster,
)

# PIR generation threshold (BEACON: composite < 12 -> collection plan only)
_PIR_THRESHOLD = 12

# Validity windows by intelligence level
_VALIDITY_DAYS: dict[str, int] = {
    "strategic": 365,
    "operational": 180,
    "tactical": 30,
}


def build_pirs(
    context: BusinessContext,
    clusters: list[ThreatCluster],
    scores: list[RiskScore],
    assets: list[AssetTag],
    *,
    llm: LLMClient | None = None,
) -> PIROutput:
    """Build SAGE-compatible PIR output from clustered threats.

    Filters clusters below threshold, generates one PIR per remaining cluster.

    Args:
        context: Business context.
        clusters: Threat clusters from pir_clusterer.
        scores: Risk scores from risk_scorer.
        assets: Mapped asset tags.
        llm: Optional LLM for description augmentation.

    Returns:
        PIROutput with generated PIR items.
    """
    now = datetime.now(timezone.utc)
    pir_items: list[PIRItem] = []

    # Build score lookup by family
    score_by_family: dict[str, RiskScore] = {}
    for cluster in clusters:
        # Find the best score for this cluster
        best_score: RiskScore | None = None
        for profile in cluster.profiles:
            for score in scores:
                if score.composite >= (best_score.composite if best_score else 0):
                    best_score = score
        if best_score:
            score_by_family[cluster.family] = best_score

    for i, cluster in enumerate(clusters):
        score = score_by_family.get(cluster.family)
        if score is None:
            continue

        # Filter below threshold
        if score.composite < _PIR_THRESHOLD:
            continue

        pir_id = f"PIR-{i + 1:03d}"
        level = score.intelligence_level
        validity_days = _VALIDITY_DAYS.get(level, 30)

        valid_from = now.isoformat()
        valid_until = (now + timedelta(days=validity_days)).isoformat()

        # Build description and collection focus
        if llm is not None:
            desc, rationale, focus, action = _llm_generate(
                context,
                cluster,
                score,
                llm,
            )
        else:
            desc = _default_description(context, cluster)
            rationale = _default_rationale(context, cluster, score)
            focus = _default_collection_focus(cluster)
            action = _default_action(cluster)

        # Asset weight rules
        weight_rules = [AssetWeightRule(tag=tag, multiplier=1.0) for tag in cluster.asset_tags[:10]]

        pir_items.append(
            PIRItem(
                pir_id=pir_id,
                intelligence_level=level,
                description=desc,
                rationale=rationale,
                collection_focus=focus,
                recommended_action=action,
                threat_actor_tags=cluster.asset_tags,
                asset_weight_rules=weight_rules,
                valid_from=valid_from,
                valid_until=valid_until,
                risk_score=score,
            )
        )

    return PIROutput(
        organization=context.organization.name,
        pir_items=pir_items,
        metadata={
            "total_clusters": len(clusters),
            "filtered_below_threshold": len(clusters) - len(pir_items),
            "threshold": _PIR_THRESHOLD,
        },
    )


def _default_description(ctx: BusinessContext, cluster: ThreatCluster) -> str:
    """Generate template-based PIR description (--no-llm mode)."""
    org = ctx.organization
    family = cluster.family.replace("_", " ").title()
    return (
        f"What {family} threat actors are actively targeting "
        f"{org.industry} organizations in {', '.join(org.geography)}?"
    )


def _default_rationale(
    ctx: BusinessContext,
    cluster: ThreatCluster,
    score: RiskScore,
) -> str:
    """Generate template-based rationale."""
    parts = [
        f"{ctx.organization.name} operates in {ctx.organization.industry}",
        f"with presence in {', '.join(ctx.organization.geography)}",
    ]
    if cluster.profiles:
        n_groups = sum(len(p.notable_groups) for p in cluster.profiles)
        if n_groups > 0:
            parts.append(f"and {n_groups} known threat groups match this profile")
    return ", ".join(parts) + "."


def _default_collection_focus(cluster: ThreatCluster) -> list[str]:
    """Generate template-based collection priorities."""
    focus: list[str] = []
    families = set()
    for p in cluster.profiles:
        families.update(p.matched_categories)

    focus.append(f"Monitor threat intelligence feeds for {cluster.family} activity")

    if cluster.asset_tags:
        focus.append(f"Assess exposure of assets tagged: {', '.join(cluster.asset_tags[:5])}")

    ttps: set[str] = set()
    for p in cluster.profiles:
        ttps.update(p.ttps[:5])
    if ttps:
        focus.append(f"Track TTPs: {', '.join(sorted(ttps)[:5])}")

    groups: list[str] = []
    for p in cluster.profiles:
        groups.extend(p.notable_groups[:3])
    if groups:
        focus.append(f"Track activity of: {', '.join(groups[:5])}")

    return focus[:5]


def _default_action(cluster: ThreatCluster) -> str:
    """Generate default recommended action."""
    return (
        f"Review and prioritize defenses against {cluster.family.replace('_', ' ')} "
        f"threats targeting identified asset categories."
    )


def _llm_generate(
    ctx: BusinessContext,
    cluster: ThreatCluster,
    score: RiskScore,
    llm: LLMClient,
) -> tuple[str, str, list[str], str]:
    """Use LLM to generate PIR content."""
    cluster_data = {
        "organization": ctx.organization.name,
        "industry": ctx.organization.industry,
        "geography": ctx.organization.geography,
        "threat_family": cluster.family,
        "asset_tags": cluster.asset_tags,
        "notable_groups": [g for p in cluster.profiles for g in p.notable_groups[:3]][:10],
        "risk_composite": score.composite,
        "intelligence_level": score.intelligence_level,
    }

    system, user = build_guarded_prompt(
        "pir_generation",
        json.dumps(cluster_data, ensure_ascii=False),
        tag_prefix="cluster",
    )

    try:
        result = llm.complete_json(system, user)
        return (
            result.get("description", _default_description(ctx, cluster)),
            result.get("rationale", _default_rationale(ctx, cluster, score)),
            result.get("collection_focus", _default_collection_focus(cluster)),
            result.get("recommended_action", _default_action(cluster)),
        )
    except Exception:
        # Fallback to templates on LLM failure
        return (
            _default_description(ctx, cluster),
            _default_rationale(ctx, cluster, score),
            _default_collection_focus(cluster),
            _default_action(cluster),
        )
