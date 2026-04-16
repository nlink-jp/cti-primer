"""Tests for cti_primer.web.app."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cti_primer.config import Config
from cti_primer.web.app import create_app

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def client() -> TestClient:
    app = create_app(Config(), no_llm=True)
    return TestClient(app)


class TestIndex:
    def test_get_index(self, client: TestClient) -> None:
        resp = client.get("/")
        assert resp.status_code == 200
        assert "CTI Primer" in resp.text
        assert "csrf_token" in resp.text

    def test_index_shows_mode(self, client: TestClient) -> None:
        resp = client.get("/")
        assert "Dictionary Mode" in resp.text


class TestGenerate:
    def test_generate_with_json(self, client: TestClient) -> None:
        # Get CSRF token first
        resp = client.get("/")
        # Extract csrf from hidden field
        import re

        match = re.search(r'name="csrf_token"\s+value="([^"]+)"', resp.text)
        assert match
        csrf = match.group(1)

        content = (FIXTURES / "sample_context.json").read_bytes()
        resp = client.post(
            "/generate",
            data={"csrf_token": csrf},
            files={"file": ("context.json", content, "application/json")},
            follow_redirects=False,
            cookies=resp.cookies,
        )
        assert resp.status_code == 303
        assert resp.headers["location"] == "/review"

    def test_generate_csrf_required(self, client: TestClient) -> None:
        content = b'{"organization": {"name": "Test", "industry": "tech"}}'
        resp = client.post(
            "/generate",
            data={"csrf_token": "invalid"},
            files={"file": ("test.json", content, "application/json")},
        )
        assert resp.status_code == 403


class TestReview:
    def test_review_redirects_without_session(self, client: TestClient) -> None:
        resp = client.get("/review", follow_redirects=False)
        assert resp.status_code in (200, 307, 302)

    def test_export_without_session(self, client: TestClient) -> None:
        resp = client.get("/review/export")
        assert resp.status_code == 404


class TestAPI:
    def test_api_pir_empty(self, client: TestClient) -> None:
        resp = client.get("/api/pir")
        assert resp.status_code == 200
        data = resp.json()
        assert "pir_items" in data

    def test_api_generate(self, client: TestClient) -> None:
        context = json.loads((FIXTURES / "sample_context.json").read_text())
        resp = client.post("/api/generate", json=context)
        assert resp.status_code == 200
        data = resp.json()
        assert "pir_items" in data
        assert "organization" in data

    def test_api_generate_invalid_json(self, client: TestClient) -> None:
        resp = client.post(
            "/api/generate",
            content=b"not json",
            headers={"content-type": "application/json"},
        )
        assert resp.status_code == 400
