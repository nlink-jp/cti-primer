"""Business context parsing — JSON and Markdown inputs.

Converts user-supplied documents into validated BusinessContext models.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from cti_primer.llm.client import LLMClient
from cti_primer.llm.prompts import build_guarded_prompt
from cti_primer.models import BusinessContext


class ParseError(Exception):
    """Raised when input cannot be parsed into BusinessContext."""


def parse_json(raw: str) -> BusinessContext:
    """Parse JSON string directly into BusinessContext.

    Args:
        raw: JSON string conforming to BusinessContext schema.

    Returns:
        Validated BusinessContext.

    Raises:
        ParseError: On invalid JSON or schema validation failure.
    """
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Invalid JSON: {exc}") from exc

    try:
        return BusinessContext(**data)
    except ValidationError as exc:
        raise ParseError(f"Schema validation failed: {exc}") from exc


def parse_markdown(raw: str, llm: LLMClient) -> BusinessContext:
    """Use LLM to structure free-form Markdown into BusinessContext.

    Args:
        raw: Markdown business strategy document.
        llm: LLM client for structuring.

    Returns:
        Validated BusinessContext.

    Raises:
        ParseError: On LLM or validation failure.
    """
    system, user = build_guarded_prompt(
        "context_structuring",
        raw,
        tag_prefix="strategy_doc",
    )

    try:
        data: dict[str, Any] = llm.complete_json(system, user)
    except Exception as exc:
        raise ParseError(f"LLM structuring failed: {exc}") from exc

    try:
        return BusinessContext(**data)
    except ValidationError as exc:
        raise ParseError(f"LLM output validation failed: {exc}") from exc


def parse_file(path: Path, llm: LLMClient | None = None) -> BusinessContext:
    """Parse a file into BusinessContext, dispatching by extension.

    Args:
        path: Path to .json or .md file.
        llm: LLM client (required for .md files).

    Returns:
        Validated BusinessContext.

    Raises:
        ParseError: On parse failure or missing LLM for Markdown.
    """
    raw = path.read_text(encoding="utf-8")

    if path.suffix.lower() == ".json":
        return parse_json(raw)

    if path.suffix.lower() in (".md", ".markdown"):
        if llm is None:
            raise ParseError("Markdown parsing requires LLM. Use --no-llm with JSON input, or provide an LLM endpoint.")
        return parse_markdown(raw, llm)

    raise ParseError(f"Unsupported file format: {path.suffix}")
