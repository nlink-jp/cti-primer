"""GitHub/GHE Issue creation for PIR review workflow.

Creates one Issue per PIR item for analyst review and approval.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from cti_primer.config import GitHubConfig
from cti_primer.models import PIROutput

logger = logging.getLogger(__name__)


class GitHubReviewError(Exception):
    """Raised when GitHub issue creation fails."""


class GitHubReviewer:
    """Creates GitHub Issues for PIR review."""

    def __init__(
        self,
        config: GitHubConfig,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        token = os.environ.get(config.token_env, "")
        if not token:
            raise GitHubReviewError(f"GitHub token not found. Set {config.token_env} environment variable.")
        if not config.repo:
            raise GitHubReviewError("GitHub repo not configured.")

        base_url = f"https://{config.host}" if config.host else "https://api.github.com"
        self._http = http_client or httpx.Client(
            base_url=base_url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
            },
            timeout=30,
        )
        self._repo = config.repo

    def create_issues(self, pir: PIROutput) -> list[str]:
        """Create one GitHub Issue per PIR item.

        Args:
            pir: PIR output to submit.

        Returns:
            List of created issue URLs.

        Raises:
            GitHubReviewError: On API failure.
        """
        urls: list[str] = []

        for item in pir.pir_items:
            title = f"[PIR] {item.pir_id}: {item.description[:80]}"
            body = self._build_issue_body(item, pir.organization)

            try:
                resp = self._http.post(
                    f"/repos/{self._repo}/issues",
                    json={
                        "title": title,
                        "body": body,
                        "labels": ["pir", item.intelligence_level],
                    },
                )
                resp.raise_for_status()
                data = resp.json()
                urls.append(data.get("html_url", ""))
                logger.info("Created issue: %s", data.get("html_url"))
            except httpx.HTTPError as exc:
                logger.error("Failed to create issue for %s: %s", item.pir_id, exc)
                raise GitHubReviewError(f"Failed to create issue for {item.pir_id}: {exc}") from exc

        return urls

    def _build_issue_body(self, item: Any, org: str) -> str:
        """Format PIR item as Markdown issue body."""
        lines = [
            f"## {item.pir_id} — {item.intelligence_level.upper()}",
            "",
            f"**Organization:** {org}",
            "",
            "### Description",
            item.description,
            "",
            "### Rationale",
            item.rationale or "_Not provided_",
            "",
            "### Collection Focus",
        ]

        for focus in item.collection_focus:
            lines.append(f"- {focus}")

        lines.extend(
            [
                "",
                "### Recommended Action",
                item.recommended_action or "_Not provided_",
                "",
                "### Threat Actor Tags",
                ", ".join(f"`{t}`" for t in item.threat_actor_tags) or "_None_",
                "",
                f"**Valid:** {item.valid_from[:10]} — {item.valid_until[:10]}",
                "",
                "---",
                "",
                "### Review Checklist",
                "- [ ] Description accurately represents the intelligence gap",
                "- [ ] Rationale is sound and specific to this organization",
                "- [ ] Collection sources are actionable",
                "- [ ] Risk assessment is appropriate",
                "- [ ] Approved for operational use",
            ]
        )

        return "\n".join(lines)

    def close(self) -> None:
        """Close the HTTP client."""
        self._http.close()
