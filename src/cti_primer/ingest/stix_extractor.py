"""Extract STIX 2.1 objects from CTI report text via LLM.

Uses nlk.guard for prompt injection defense on untrusted report content.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from cti_primer.llm.client import LLMClient
from cti_primer.llm.prompts import build_guarded_prompt

logger = logging.getLogger(__name__)

_VALID_STIX_TYPES = frozenset(
    {
        "threat-actor",
        "intrusion-set",
        "attack-pattern",
        "malware",
        "tool",
        "vulnerability",
        "indicator",
        "relationship",
    }
)


class StixExtractionError(Exception):
    """Raised when STIX extraction fails."""


def extract_stix(text: str, llm: LLMClient) -> dict[str, Any]:
    """Extract STIX 2.1 objects from report text.

    Args:
        text: Report text content.
        llm: LLM client for extraction.

    Returns:
        STIX 2.1 bundle dict.
    """
    system, user = build_guarded_prompt(
        "stix_extraction",
        text,
        tag_prefix="report",
    )

    try:
        raw_objects = llm.complete_json(system, user)
    except Exception as exc:
        raise StixExtractionError(f"LLM extraction failed: {exc}") from exc

    if not isinstance(raw_objects, list):
        raw_objects = [raw_objects]

    validated = _validate_objects(raw_objects)
    return build_stix_bundle(validated)


def build_stix_bundle(objects: list[dict[str, Any]]) -> dict[str, Any]:
    """Wrap STIX objects in a STIX 2.1 bundle.

    Args:
        objects: List of STIX 2.1 objects.

    Returns:
        STIX 2.1 bundle dict.
    """
    now = datetime.now(timezone.utc).isoformat()

    return {
        "type": "bundle",
        "id": f"bundle--{uuid.uuid4()}",
        "spec_version": "2.1",
        "created": now,
        "objects": objects,
    }


def _validate_objects(raw: list[Any]) -> list[dict[str, Any]]:
    """Validate and clean STIX objects from LLM output."""
    valid: list[dict[str, Any]] = []

    for obj in raw:
        if not isinstance(obj, dict):
            continue

        stix_type = obj.get("type", "")
        if stix_type not in _VALID_STIX_TYPES:
            logger.warning("Skipping invalid STIX type: %s", stix_type)
            continue

        # Ensure required fields
        if "id" not in obj:
            obj["id"] = f"{stix_type}--{uuid.uuid4()}"

        if "spec_version" not in obj:
            obj["spec_version"] = "2.1"

        now = datetime.now(timezone.utc).isoformat()
        if "created" not in obj:
            obj["created"] = now
        if "modified" not in obj:
            obj["modified"] = now

        # Validate name for non-relationship objects
        if stix_type != "relationship" and not obj.get("name"):
            logger.warning("Skipping %s without name", stix_type)
            continue

        valid.append(obj)

    return valid
