"""Cluster threats into focused PIR groups by threat family.

Groups related threat profiles for generating distinct PIR items.
"""

from __future__ import annotations

from cti_primer.models import RiskScore, ThreatCluster, ThreatProfile

# 8 threat families (from BEACON)
THREAT_FAMILIES: dict[str, set[str]] = {
    "ransomware": {"ransomware", "lockbit", "blackcat", "clop", "rhysida", "akira"},
    "financial_crime": {"financial-gain", "cybercriminal", "bec", "fraud"},
    "supply_chain": {"supply-chain", "third-party", "msp"},
    "cloud_targeting": {"cloud", "saas", "kubernetes", "container"},
    "state_sponsored": {"apt-china", "apt-russia", "apt-northkorea", "apt-iran", "espionage", "ip-theft"},
    "ot_ics": {"ot", "ics", "scada", "critical-infrastructure", "sabotage"},
    "hacktivism": {"hacktivism", "ddos", "defacement"},
    "insider_threat": {"insider-threat", "insider"},
}

_MAX_CLUSTERS = 5


def cluster_threats(
    profiles: list[ThreatProfile],
    scores: list[RiskScore],
    *,
    max_clusters: int = _MAX_CLUSTERS,
) -> list[ThreatCluster]:
    """Group threat profiles into clusters by threat family.

    Args:
        profiles: Matched threat profiles.
        scores: Corresponding risk scores (same length as profiles).
        max_clusters: Maximum number of clusters to return.

    Returns:
        List of ThreatClusters sorted by aggregate score (descending).
    """
    if not profiles:
        return []

    # Map profiles to families
    family_groups: dict[str, list[tuple[ThreatProfile, RiskScore]]] = {}

    for profile, score in zip(profiles, scores):
        family = _detect_family(profile)
        if family not in family_groups:
            family_groups[family] = []
        family_groups[family].append((profile, score))

    # Build clusters
    clusters: list[ThreatCluster] = []
    for family, members in family_groups.items():
        combined_profiles = [m[0] for m in members]
        agg_score = max(m[1].composite for m in members)

        # Collect unique asset-relevant tags
        all_tags: set[str] = set()
        for p, _ in members:
            all_tags.update(p.actor_tags)

        clusters.append(
            ThreatCluster(
                family=family,
                profiles=combined_profiles,
                asset_tags=sorted(all_tags),
                aggregate_score=agg_score,
            )
        )

    # Sort by score, limit
    clusters.sort(key=lambda c: c.aggregate_score, reverse=True)
    return clusters[:max_clusters]


def _detect_family(profile: ThreatProfile) -> str:
    """Detect which threat family a profile belongs to."""
    # If profile already has a family set, use it
    if profile.threat_family:
        # Normalize state_sponsored variants
        for family_name in THREAT_FAMILIES:
            if family_name in profile.threat_family:
                return family_name

    # Match by tags
    tag_set = set(t.lower() for t in profile.actor_tags)
    best_family = "general"
    best_overlap = 0

    for family_name, family_tags in THREAT_FAMILIES.items():
        overlap = len(tag_set & family_tags)
        if overlap > best_overlap:
            best_overlap = overlap
            best_family = family_name

    return best_family
