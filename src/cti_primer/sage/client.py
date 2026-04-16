"""SAGE API client with fail-open semantics.

All methods return None/0/empty on any error — pipeline continues without SAGE data.
"""

from __future__ import annotations

import logging

import httpx

from cti_primer.config import SAGEConfig

logger = logging.getLogger(__name__)


class SAGEClient:
    """Client for SAGE Analysis API."""

    def __init__(
        self,
        config: SAGEConfig,
        http_client: httpx.Client | None = None,
    ) -> None:
        self._config = config
        self._http = http_client or httpx.Client(
            base_url=config.api_url,
            timeout=config.timeout,
        )

    def get_observation_counts(self, tags: list[str]) -> dict[str, int]:
        """Fetch observation counts for actor tags.

        Args:
            tags: List of threat actor tags.

        Returns:
            Dict mapping tag -> observation count.
            Returns empty dict on any error.
        """
        try:
            resp = self._http.get(
                "/asset-exposure",
                params={"tags": ",".join(tags)},
            )
            resp.raise_for_status()
            data = resp.json()

            counts: dict[str, int] = {}
            for actor in data.get("actors", []):
                actor_tags = set(actor.get("tags", []))
                for tag in tags:
                    if tag in actor_tags:
                        counts[tag] = counts.get(tag, 0) + 1

            return counts

        except httpx.TimeoutException:
            logger.warning("SAGE API timeout")
        except httpx.HTTPError as exc:
            logger.warning("SAGE API error: %s", exc)
        except Exception as exc:
            logger.warning("SAGE API unexpected error: %s", exc)

        return {}

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._http.close()
