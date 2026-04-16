"""Prompt template loading and guard integration."""

from __future__ import annotations

from pathlib import Path

from nlk.guard import Tag

_PROMPTS_DIR = Path(__file__).parent


def load_prompt(name: str) -> str:
    """Load a prompt template from the prompts/ directory.

    Args:
        name: Template name without extension (e.g. "context_structuring").

    Returns:
        Template content as string.

    Raises:
        FileNotFoundError: If template does not exist.
    """
    path = _PROMPTS_DIR / f"{name}.md"
    return path.read_text(encoding="utf-8")


def build_guarded_prompt(
    template_name: str,
    untrusted_data: str,
    *,
    tag_prefix: str = "context",
) -> tuple[str, str]:
    """Load template and create nlk.guard-protected prompt pair.

    Creates a fresh nonce Tag per call (required by nlk.guard safety model).

    Args:
        template_name: Prompt template name.
        untrusted_data: User-supplied data to wrap.
        tag_prefix: Prefix for the nonce tag.

    Returns:
        Tuple of (system_prompt, user_content) with guard tags applied.
    """
    tag = Tag.new(tag_prefix)
    template = load_prompt(template_name)
    system = tag.expand(template)
    user = tag.wrap(untrusted_data)
    return system, user
