"""Generate SAGE-compatible assets.json from BusinessContext.

Converts organizational asset inventory into the format consumed by SAGE.
"""

from __future__ import annotations

from typing import Any

from cti_primer.models import BusinessContext, CriticalAsset

# Asset type normalization
_TYPE_MAP: dict[str, str] = {
    "server": "server",
    "endpoint": "endpoint",
    "network-device": "network-device",
    "cloud": "cloud",
    "ot-controller": "ot-controller",
    "ot": "ot-controller",
    "ics": "ot-controller",
}

# Criticality to numeric score
_CRITICALITY_MAP: dict[str, float] = {
    "critical": 10.0,
    "high": 7.5,
    "medium": 5.0,
    "low": 2.5,
}

# Zone to network segment mapping
_ZONE_CIDR: dict[str, str] = {
    "internal": "10.0.0.0/8",
    "dmz": "172.16.0.0/12",
    "ot": "192.168.0.0/16",
    "internet": "0.0.0.0/0",
}


def generate_assets(context: BusinessContext) -> dict[str, Any]:
    """Convert BusinessContext to SAGE-compatible assets JSON.

    Returns:
        Dict with keys: network_segments, assets, connections.
    """
    segments = _build_segments(context)
    assets = _build_assets(context)
    connections = _build_connections(context)

    return {
        "organization": context.organization.name,
        "network_segments": segments,
        "assets": assets,
        "connections": connections,
    }


def _build_segments(context: BusinessContext) -> list[dict[str, Any]]:
    """Build network segments from unique zones."""
    zones: set[str] = set()
    for asset in context.critical_assets:
        if asset.network_zone:
            zones.add(asset.network_zone.lower())

    segments: list[dict[str, Any]] = []
    for zone in sorted(zones):
        segments.append(
            {
                "segment_id": f"seg-{zone}",
                "name": zone.title(),
                "cidr": _ZONE_CIDR.get(zone, "10.0.0.0/8"),
                "zone": zone,
            }
        )

    return segments


def _build_assets(context: BusinessContext) -> list[dict[str, Any]]:
    """Build asset list from critical assets."""
    assets: list[dict[str, Any]] = []

    for ca in context.critical_assets:
        asset_id = ca.asset_id
        if not asset_id.startswith("asset-"):
            asset_id = f"asset-{asset_id}"

        asset_type = _TYPE_MAP.get(ca.asset_type, ca.asset_type or "server")
        criticality = _CRITICALITY_MAP.get(ca.criticality, 5.0)

        tags = _derive_tags(ca)
        is_internet_facing = ca.network_zone.lower() in ("dmz", "internet")

        assets.append(
            {
                "asset_id": asset_id,
                "hostname": ca.hostname,
                "os": ca.os,
                "asset_type": asset_type,
                "network_segment": f"seg-{ca.network_zone.lower()}" if ca.network_zone else "",
                "criticality": criticality,
                "tags": tags,
                "is_internet_facing": is_internet_facing,
                "owner": "",
                "security_control_ids": [],
                "asset_vulnerabilities": [],
                "actor_targets": [],
            }
        )

    return assets


def _derive_tags(asset: CriticalAsset) -> list[str]:
    """Derive asset tags from properties."""
    tags: set[str] = set()

    # From asset type
    if asset.asset_type in ("ot-controller", "ot", "ics"):
        tags.add("ot")
    elif "db" in asset.hostname.lower() or "database" in asset.asset_type.lower():
        tags.add("database")
    elif "sap" in asset.hostname.lower() or "erp" in asset.hostname.lower():
        tags.add("erp")

    # From network zone
    zone = asset.network_zone.lower()
    if zone in ("dmz", "internet"):
        tags.add("external-facing")
    elif zone == "ot":
        tags.add("ot")

    return sorted(tags)


def _build_connections(context: BusinessContext) -> list[dict[str, Any]]:
    """Build asset connections from dependency declarations."""
    connections: list[dict[str, Any]] = []
    known_ids = {ca.asset_id for ca in context.critical_assets}

    for ca in context.critical_assets:
        for dep in ca.dependencies:
            if dep in known_ids:
                connections.append(
                    {
                        "from_asset": ca.asset_id,
                        "to_asset": dep,
                        "connection_type": "depends_on",
                    }
                )

    return connections
