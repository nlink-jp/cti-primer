"""Risk scoring — likelihood × impact with SAGE boost.

Pure functions for calculating composite risk scores and intelligence levels.
"""

from __future__ import annotations

from cti_primer.models import AssetTag, BusinessContext, RiskScore, ThreatProfile

# Impact mapping from crown jewel business_impact
_IMPACT_MAP: dict[str, int] = {
    "critical": 5,
    "high": 4,
    "medium": 3,
    "low": 2,
}

# Intelligence level thresholds (based on composite score)
_STRATEGIC_THRESHOLD = 20
_OPERATIONAL_THRESHOLD = 12

# High-risk triggers that boost to operational
_HIGH_RISK_TRIGGERS = frozenset(
    {
        "ot_connectivity",
        "ma_activity",
        "publicly_listed",
    }
)


def score_risks(
    context: BusinessContext,
    profiles: list[ThreatProfile],
    assets: list[AssetTag],
    triggers: list[str],
    *,
    sage_observations: dict[str, int] | None = None,
) -> list[RiskScore]:
    """Calculate risk scores for each threat profile.

    Args:
        context: Business context for impact derivation.
        profiles: Matched threat profiles.
        assets: Mapped asset tags.
        triggers: Detected business triggers.
        sage_observations: Optional SAGE observation counts by actor tag.

    Returns:
        List of RiskScores, one per threat profile.
    """
    impact = _derive_impact(context)

    scores: list[RiskScore] = []
    for profile in profiles:
        likelihood = _calculate_likelihood(profile, triggers)

        # SAGE boost
        sage_boosted = False
        if sage_observations:
            for tag in profile.actor_tags:
                if sage_observations.get(tag, 0) >= 1:
                    likelihood = min(likelihood + 1, 5)
                    sage_boosted = True
                    break

        composite = likelihood * impact
        level = classify_intelligence_level(composite, triggers)

        rationale = _build_rationale(profile, likelihood, impact, sage_boosted)

        scores.append(
            RiskScore(
                likelihood=likelihood,
                impact=impact,
                composite=float(composite),
                sage_boosted=sage_boosted,
                intelligence_level=level,
                rationale=rationale,
            )
        )

    return scores


def classify_intelligence_level(composite: float, triggers: list[str]) -> str:
    """Classify intelligence level based on composite score.

    - strategic: composite >= 20
    - operational: composite >= 12, or active high-risk triggers
    - tactical: composite < 12
    """
    if composite >= _STRATEGIC_THRESHOLD:
        return "strategic"

    if composite >= _OPERATIONAL_THRESHOLD:
        return "operational"

    # High-risk triggers can boost to operational
    if any(t in _HIGH_RISK_TRIGGERS for t in triggers):
        return "operational"

    return "tactical"


def _derive_impact(context: BusinessContext) -> int:
    """Derive impact score from highest crown jewel business_impact."""
    if not context.crown_jewels:
        return 2  # default low-medium

    max_impact = 2
    for cj in context.crown_jewels:
        score = _IMPACT_MAP.get(cj.business_impact, 2)
        max_impact = max(max_impact, score)

    return max_impact


def _calculate_likelihood(
    profile: ThreatProfile,
    triggers: list[str],
) -> int:
    """Calculate base likelihood from profile match quality.

    Base scoring:
      - 0 matched categories: 1
      - 1 matched category: 2
      - 2 matched categories: 3
      - 3+ matched categories: 4

    Trigger boost: +1 if any business trigger active.
    Capped at 5.
    """
    n_categories = len(profile.matched_categories)

    if n_categories == 0:
        base = 1
    elif n_categories == 1:
        base = 2
    elif n_categories == 2:
        base = 3
    else:
        base = 4

    # Notable groups boost (more known groups = higher confidence)
    if len(profile.notable_groups) >= 5:
        base = min(base + 1, 5)

    # Trigger boost
    if triggers:
        base = min(base + 1, 5)

    return base


def _build_rationale(
    profile: ThreatProfile,
    likelihood: int,
    impact: int,
    sage_boosted: bool,
) -> str:
    """Build human-readable rationale string."""
    parts: list[str] = []

    if profile.matched_categories:
        parts.append(f"Matched categories: {', '.join(profile.matched_categories)}")

    if profile.notable_groups:
        groups = profile.notable_groups[:5]
        parts.append(f"Notable groups: {', '.join(groups)}")

    parts.append(f"Likelihood={likelihood}, Impact={impact}")

    if sage_boosted:
        parts.append("SAGE observation boost applied")

    return ". ".join(parts)
