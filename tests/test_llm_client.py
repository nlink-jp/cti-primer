"""Tests for cti_primer.llm.client."""

from __future__ import annotations

import httpx
import pytest
import respx

from cti_primer.config import LLMConfig
from cti_primer.llm.client import (
    HttpxLLMClient,
    LLMError,
    LLMJsonError,
    NoLLMClient,
)


def _make_config(**kwargs) -> LLMConfig:
    defaults = {
        "endpoint": "http://localhost:1234/v1",
        "model": "test-model",
        "api_key": "",
        "timeout": 5,
    }
    defaults.update(kwargs)
    return LLMConfig(**defaults)


def _chat_response(content: str) -> dict:
    return {
        "choices": [{"message": {"content": content}}],
    }


# ---------------------------------------------------------------------------
# HttpxLLMClient tests
# ---------------------------------------------------------------------------


class TestComplete:
    @respx.mock
    def test_basic_completion(self) -> None:
        respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_chat_response("Hello world"))
        )
        client = HttpxLLMClient(_make_config())
        result = client.complete("system", "user")
        assert result == "Hello world"

    @respx.mock
    def test_strips_thinking_tags(self) -> None:
        respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json=_chat_response("<think>internal reasoning</think>The answer is 42"),
            )
        )
        client = HttpxLLMClient(_make_config())
        result = client.complete("system", "user")
        assert result == "The answer is 42"
        assert "<think>" not in result

    @respx.mock
    def test_strips_gemma4_thinking(self) -> None:
        respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json=_chat_response("<|channel>thought\nLet me think...\n<channel|>Result here"),
            )
        )
        client = HttpxLLMClient(_make_config())
        result = client.complete("system", "user")
        assert result == "Result here"

    @respx.mock
    def test_api_key_sent_in_header(self) -> None:
        route = respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_chat_response("ok"))
        )
        client = HttpxLLMClient(_make_config(api_key="sk-test-123"))
        client.complete("system", "user")
        assert route.calls[0].request.headers["Authorization"] == "Bearer sk-test-123"

    @respx.mock
    def test_no_auth_header_when_no_key(self) -> None:
        route = respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(200, json=_chat_response("ok"))
        )
        client = HttpxLLMClient(_make_config(api_key=""))
        client.complete("system", "user")
        assert "Authorization" not in route.calls[0].request.headers


class TestCompleteJson:
    @respx.mock
    def test_parses_json(self) -> None:
        respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json=_chat_response('{"category": "safe", "confidence": 0.9}'),
            )
        )
        client = HttpxLLMClient(_make_config())
        result = client.complete_json("system", "user")
        assert result["category"] == "safe"
        assert result["confidence"] == 0.9

    @respx.mock
    def test_repairs_malformed_json(self) -> None:
        respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json=_chat_response("```json\n{'key': 'value',}\n```"),
            )
        )
        client = HttpxLLMClient(_make_config())
        result = client.complete_json("system", "user")
        assert result["key"] == "value"

    @respx.mock
    def test_json_with_thinking_tags(self) -> None:
        respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json=_chat_response('<think>analyzing...</think>{"result": true}'),
            )
        )
        client = HttpxLLMClient(_make_config())
        result = client.complete_json("system", "user")
        assert result["result"] is True

    @respx.mock
    def test_raises_on_no_json(self) -> None:
        respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(
                200,
                json=_chat_response("This is plain text with no JSON"),
            )
        )
        client = HttpxLLMClient(_make_config())
        with pytest.raises(LLMJsonError):
            client.complete_json("system", "user")


class TestRetry:
    @respx.mock
    def test_retries_on_429(self) -> None:
        route = respx.post("http://localhost:1234/v1/chat/completions")
        route.side_effect = [
            httpx.Response(429, text="rate limited"),
            httpx.Response(200, json=_chat_response("success")),
        ]
        client = HttpxLLMClient(_make_config())
        result = client.complete("system", "user")
        assert result == "success"
        assert route.call_count == 2

    @respx.mock
    def test_retries_on_500(self) -> None:
        route = respx.post("http://localhost:1234/v1/chat/completions")
        route.side_effect = [
            httpx.Response(500, text="internal error"),
            httpx.Response(200, json=_chat_response("recovered")),
        ]
        client = HttpxLLMClient(_make_config())
        result = client.complete("system", "user")
        assert result == "recovered"

    @respx.mock
    def test_fails_after_max_retries(self) -> None:
        respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(500, text="persistent error")
        )
        client = HttpxLLMClient(_make_config())
        with pytest.raises(LLMError, match="failed after"):
            client.complete("system", "user")

    @respx.mock
    def test_non_retryable_error_fails_immediately(self) -> None:
        respx.post("http://localhost:1234/v1/chat/completions").mock(
            return_value=httpx.Response(400, text="bad request")
        )
        client = HttpxLLMClient(_make_config())
        with pytest.raises(LLMError, match="Non-retryable"):
            client.complete("system", "user")


# ---------------------------------------------------------------------------
# NoLLMClient tests
# ---------------------------------------------------------------------------


class TestNoLLMClient:
    def test_complete_raises(self) -> None:
        client = NoLLMClient()
        with pytest.raises(LLMError, match="no-llm"):
            client.complete("system", "user")

    def test_complete_json_raises(self) -> None:
        client = NoLLMClient()
        with pytest.raises(LLMError, match="no-llm"):
            client.complete_json("system", "user")

    def test_is_llm_client(self) -> None:
        from cti_primer.llm.client import LLMClient

        assert isinstance(NoLLMClient(), LLMClient)


# ---------------------------------------------------------------------------
# Prompt template tests
# ---------------------------------------------------------------------------


class TestPromptTemplates:
    def test_load_prompt(self) -> None:
        from cti_primer.llm.prompts import load_prompt

        content = load_prompt("context_structuring")
        assert "{{DATA_TAG}}" in content

    def test_load_nonexistent_raises(self) -> None:
        from cti_primer.llm.prompts import load_prompt

        with pytest.raises(FileNotFoundError):
            load_prompt("nonexistent_template")

    def test_build_guarded_prompt(self) -> None:
        from cti_primer.llm.prompts import build_guarded_prompt

        system, user = build_guarded_prompt("context_structuring", "test data")
        assert "{{DATA_TAG}}" not in system
        assert "context_" in system
        assert "<" in user
        assert "test data" in user

    def test_guard_tag_changes_each_call(self) -> None:
        from cti_primer.llm.prompts import build_guarded_prompt

        sys1, _ = build_guarded_prompt("context_structuring", "data1")
        sys2, _ = build_guarded_prompt("context_structuring", "data2")
        assert sys1 != sys2
