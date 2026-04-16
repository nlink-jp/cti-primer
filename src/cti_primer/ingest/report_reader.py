"""Read CTI reports from various sources (PDF, URL, text, Markdown).

Converts report content to plain text for STIX extraction.
"""

from __future__ import annotations

import logging
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

_MAX_CHARS = 30_000
_ALLOWED_SCHEMES = frozenset({"http", "https"})


class ReportReadError(Exception):
    """Raised when report cannot be read."""


def read_source(source: str) -> str:
    """Read report from file path or URL.

    Args:
        source: File path or URL string.

    Returns:
        Report text content.
    """
    if source.startswith(("http://", "https://")):
        return read_url(source)
    return read_file(Path(source))


def read_file(path: Path) -> str:
    """Read report from file, dispatching by extension.

    Supports: .pdf, .md, .txt, .html
    """
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return read_pdf(path)
    if suffix in (".md", ".markdown", ".txt", ".text"):
        return _truncate(path.read_text(encoding="utf-8"))
    if suffix in (".html", ".htm"):
        return _read_html(path)

    # Fallback: try reading as text
    return _truncate(path.read_text(encoding="utf-8"))


def read_pdf(path: Path) -> str:
    """Extract text from PDF using pypdf."""
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise ReportReadError("pypdf is required for PDF reading") from exc

    reader = PdfReader(str(path))
    parts: list[str] = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            parts.append(text)

    return _truncate("\n".join(parts))


def read_url(url: str) -> str:
    """Fetch URL content and extract text.

    Only http and https schemes are allowed.
    """
    parsed = httpx.URL(url)
    if parsed.scheme not in _ALLOWED_SCHEMES:
        raise ReportReadError(f"Unsupported URL scheme: {parsed.scheme}")

    try:
        resp = httpx.get(url, timeout=30, follow_redirects=True)
        resp.raise_for_status()
    except httpx.HTTPError as exc:
        raise ReportReadError(f"Failed to fetch URL: {exc}") from exc

    content_type = resp.headers.get("content-type", "")

    if "text/html" in content_type:
        return _extract_html_text(resp.text)

    return _truncate(resp.text)


def _read_html(path: Path) -> str:
    """Read HTML file and extract text."""
    raw = path.read_text(encoding="utf-8")
    return _extract_html_text(raw)


def _extract_html_text(html: str) -> str:
    """Extract readable text from HTML."""
    try:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")
        # Remove script and style elements
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        text = soup.get_text(separator="\n", strip=True)
    except ImportError:
        # Fallback: strip tags manually
        import re

        text = re.sub(r"<[^>]+>", "", html)

    return _truncate(text)


def _truncate(text: str, max_chars: int = _MAX_CHARS) -> str:
    """Truncate text to max characters."""
    if len(text) <= max_chars:
        return text
    logger.warning("Truncating text from %d to %d chars", len(text), max_chars)
    return text[:max_chars]
