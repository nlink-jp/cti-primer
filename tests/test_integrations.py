"""Tests for cti_primer.sage.client and cti_primer.review.github."""

from __future__ import annotations

import httpx
import pytest
import respx

from cti_primer.config import GitHubConfig, SAGEConfig
from cti_primer.models import PIRItem, PIROutput
from cti_primer.review.github import GitHubReviewer, GitHubReviewError
from cti_primer.sage.client import SAGEClient

# ===========================================================================
# SAGE Client
# ===========================================================================


class TestSAGEClient:
    @respx.mock
    def test_get_observation_counts(self) -> None:
        respx.get("http://sage:8080/asset-exposure").mock(
            return_value=httpx.Response(
                200,
                json={
                    "actors": [
                        {"name": "APT41", "tags": ["apt-china", "espionage"]},
                        {"name": "LockBit", "tags": ["ransomware"]},
                    ]
                },
            )
        )
        client = SAGEClient(SAGEConfig(api_url="http://sage:8080"))
        counts = client.get_observation_counts(["apt-china", "ransomware", "unknown"])
        assert counts["apt-china"] == 1
        assert counts["ransomware"] == 1
        assert "unknown" not in counts

    @respx.mock
    def test_fail_open_on_timeout(self) -> None:
        respx.get("http://sage:8080/asset-exposure").mock(side_effect=httpx.TimeoutException("timeout"))
        client = SAGEClient(SAGEConfig(api_url="http://sage:8080"))
        counts = client.get_observation_counts(["apt-china"])
        assert counts == {}

    @respx.mock
    def test_fail_open_on_500(self) -> None:
        respx.get("http://sage:8080/asset-exposure").mock(return_value=httpx.Response(500))
        client = SAGEClient(SAGEConfig(api_url="http://sage:8080"))
        counts = client.get_observation_counts(["apt-china"])
        assert counts == {}

    @respx.mock
    def test_fail_open_on_connection_error(self) -> None:
        respx.get("http://sage:8080/asset-exposure").mock(side_effect=httpx.ConnectError("refused"))
        client = SAGEClient(SAGEConfig(api_url="http://sage:8080"))
        counts = client.get_observation_counts(["apt-china"])
        assert counts == {}


# ===========================================================================
# GitHub Reviewer
# ===========================================================================


class TestGitHubReviewer:
    def test_missing_token_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        with pytest.raises(GitHubReviewError, match="token not found"):
            GitHubReviewer(GitHubConfig(repo="org/repo"))

    def test_missing_repo_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        with pytest.raises(GitHubReviewError, match="repo not configured"):
            GitHubReviewer(GitHubConfig(repo=""))

    @respx.mock
    def test_create_issues(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        route = respx.post("https://api.github.com/repos/org/repo/issues").mock(
            return_value=httpx.Response(
                201,
                json={
                    "html_url": "https://github.com/org/repo/issues/1",
                },
            )
        )

        reviewer = GitHubReviewer(GitHubConfig(repo="org/repo"))
        pir = PIROutput(
            organization="Test",
            pir_items=[
                PIRItem(
                    pir_id="PIR-001",
                    intelligence_level="strategic",
                    description="Test question?",
                    rationale="Test rationale",
                    collection_focus=["Source 1"],
                    recommended_action="Do something",
                    threat_actor_tags=["apt-china"],
                    valid_from="2026-01-01",
                    valid_until="2027-01-01",
                ),
            ],
        )
        urls = reviewer.create_issues(pir)
        assert len(urls) == 1
        assert "github.com" in urls[0]

        # Check issue body contains review checklist
        req_body = route.calls[0].request.content
        import json

        body = json.loads(req_body)
        assert "PIR-001" in body["title"]
        assert "pir" in body["labels"]

    @respx.mock
    def test_ghe_host(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        respx.post("https://github.example.com/repos/org/repo/issues").mock(
            return_value=httpx.Response(
                201,
                json={
                    "html_url": "https://github.example.com/org/repo/issues/1",
                },
            )
        )

        reviewer = GitHubReviewer(
            GitHubConfig(host="github.example.com", repo="org/repo"),
        )
        pir = PIROutput(
            organization="Test",
            pir_items=[
                PIRItem(
                    pir_id="PIR-001",
                    intelligence_level="tactical",
                    description="Test?",
                    valid_from="2026-01-01",
                    valid_until="2026-02-01",
                ),
            ],
        )
        urls = reviewer.create_issues(pir)
        assert len(urls) == 1

    @respx.mock
    def test_api_error_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_TOKEN", "test-token")
        respx.post("https://api.github.com/repos/org/repo/issues").mock(
            return_value=httpx.Response(422, json={"message": "Validation Failed"})
        )

        reviewer = GitHubReviewer(GitHubConfig(repo="org/repo"))
        pir = PIROutput(
            organization="Test",
            pir_items=[
                PIRItem(
                    pir_id="PIR-001",
                    intelligence_level="tactical",
                    description="Test?",
                    valid_from="2026-01-01",
                    valid_until="2026-02-01",
                ),
            ],
        )
        with pytest.raises(GitHubReviewError):
            reviewer.create_issues(pir)
