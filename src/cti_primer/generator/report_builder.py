"""Generate collection plan Markdown report.

Produces monitoring guidance when risk scores fall below PIR thresholds,
or a summary when PIRs are generated.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from cti_primer.models import BusinessContext, PIROutput, RiskScore, ThreatCluster

_SCHEMA_DIR = Path(__file__).parent.parent.parent.parent / "schema"

_FREQUENCY_TABLE = {
    "strategic": "Quarterly",
    "operational": "Monthly",
    "tactical": "Weekly",
}


def build_report(
    context: BusinessContext,
    pir_output: PIROutput,
    clusters: list[ThreatCluster],
    scores: list[RiskScore],
) -> str:
    """Generate collection plan as Markdown string.

    Args:
        context: Business context.
        pir_output: Generated PIR output.
        clusters: All threat clusters (including filtered ones).
        scores: All risk scores.

    Returns:
        Markdown string.
    """
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    org = context.organization
    lines: list[str] = []

    # Header
    lines.append(f"# Collection Plan — {org.name}")
    lines.append("")
    lines.append(f"Generated: {now}")
    lines.append(f"Industry: {org.industry}")
    lines.append(f"Geography: {', '.join(org.geography)}")
    lines.append("")

    # PIR summary
    n_pirs = len(pir_output.pir_items)
    if n_pirs > 0:
        lines.append(f"## PIR Summary ({n_pirs} generated)")
        lines.append("")
        for item in pir_output.pir_items:
            lines.append(f"### {item.pir_id} ({item.intelligence_level})")
            lines.append("")
            lines.append(f"**Question:** {item.description}")
            lines.append("")
            if item.rationale:
                lines.append(f"**Rationale:** {item.rationale}")
                lines.append("")
            if item.collection_focus:
                lines.append("**Collection Focus:**")
                for focus in item.collection_focus:
                    lines.append(f"- {focus}")
                lines.append("")
            if item.recommended_action:
                lines.append(f"**Recommended Action:** {item.recommended_action}")
                lines.append("")
    else:
        lines.append("## Monitoring Status")
        lines.append("")
        lines.append("No threats exceeded the PIR generation threshold. The following watch items are recommended.")
        lines.append("")

    # Threat watch items (all clusters including below-threshold)
    if clusters:
        lines.append("## Threat Watch Items")
        lines.append("")
        for cluster in clusters:
            lines.append(f"### {cluster.family.replace('_', ' ').title()}")
            lines.append(f"- Aggregate score: {cluster.aggregate_score:.0f}")
            if cluster.asset_tags:
                lines.append(f"- Related asset tags: {', '.join(cluster.asset_tags[:5])}")
            for p in cluster.profiles:
                if p.notable_groups:
                    lines.append(f"- Notable groups: {', '.join(p.notable_groups[:5])}")
            lines.append("")

    # Collection frequency table
    lines.append("## Collection Frequency")
    lines.append("")
    lines.append("| Intelligence Level | Review Cadence |")
    lines.append("|---|---|")
    for level, freq in _FREQUENCY_TABLE.items():
        lines.append(f"| {level.title()} | {freq} |")
    lines.append("")

    return "\n".join(lines)


def write_report(report: str, path: Path) -> None:
    """Write report to file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")
