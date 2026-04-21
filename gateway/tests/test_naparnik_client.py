"""Tests for NaparnikClient SSE parsing and search logic."""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gateway.naparnik_client import NaparnikClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _sse_lines(*data_values: str | dict, done: bool = True) -> str:
    """Build a raw SSE response string from data payloads."""
    lines: list[str] = []
    for val in data_values:
        payload = json.dumps(val) if isinstance(val, dict) else val
        lines.append(f"data: {payload}")
    if done:
        lines.append("data: [DONE]")
    return "\n".join(lines)


def _make_client(api_key: str = "test-key") -> NaparnikClient:
    return NaparnikClient(api_key=api_key)


# ---------------------------------------------------------------------------
# _parse_sse_response  --  content_delta (Format 1)
# ---------------------------------------------------------------------------

class TestParseSSEContentDelta:
    """Format 1: content_delta field."""

    def test_content_delta_string(self):
        raw = _sse_lines(
            {"content_delta": "Hello "},
            {"content_delta": "world!"},
        )
        assert _make_client()._parse_sse_response(raw) == "Hello world!"

    def test_content_delta_dict(self):
        raw = _sse_lines(
            {"content_delta": {"content": "chunk1"}},
            {"content_delta": {"content": "chunk2"}},
        )
        assert _make_client()._parse_sse_response(raw) == "chunk1chunk2"

    def test_content_delta_dict_empty_content(self):
        """Empty string in content_delta dict is skipped."""
        raw = _sse_lines(
            {"content_delta": {"content": ""}},
            {"content_delta": "real"},
        )
        assert _make_client()._parse_sse_response(raw) == "real"

    def test_content_delta_mixed(self):
        raw = _sse_lines(
            {"content_delta": "A"},
            {"content_delta": {"content": "B"}},
        )
        assert _make_client()._parse_sse_response(raw) == "AB"

    def test_content_delta_non_string_non_dict_is_ignored(self):
        raw = _sse_lines(
            {"content_delta": 123},
            {"content_delta": "ok"},
        )
        assert _make_client()._parse_sse_response(raw) == "ok"


# ---------------------------------------------------------------------------
# _parse_sse_response  --  OpenAI-like choices (Format 2)
# ---------------------------------------------------------------------------

class TestParseSSEChoices:
    """Format 2: OpenAI-style choices array."""

    def test_single_choice(self):
        raw = _sse_lines(
            {"choices": [{"delta": {"content": "alpha"}}]},
            {"choices": [{"delta": {"content": " beta"}}]},
        )
        assert _make_client()._parse_sse_response(raw) == "alpha beta"

    def test_multiple_choices(self):
        raw = _sse_lines(
            {"choices": [
                {"delta": {"content": "X"}},
                {"delta": {"content": "Y"}},
            ]},
        )
        assert _make_client()._parse_sse_response(raw) == "XY"

    def test_empty_delta_skipped(self):
        raw = _sse_lines(
            {"choices": [{"delta": {}}]},
            {"choices": [{"delta": {"content": "ok"}}]},
        )
        assert _make_client()._parse_sse_response(raw) == "ok"

    def test_null_content_skipped(self):
        raw = _sse_lines(
            {"choices": [{"delta": {"content": None}}]},
            {"choices": [{"delta": {"content": "data"}}]},
        )
        assert _make_client()._parse_sse_response(raw) == "data"


# ---------------------------------------------------------------------------
# _parse_sse_response  --  Final content (Format 3)
# ---------------------------------------------------------------------------

class TestParseSSEFinalContent:
    """Format 3: content field (dict or str)."""

    def test_content_dict_with_text(self):
        raw = _sse_lines({"content": {"text": "final answer"}})
        assert _make_client()._parse_sse_response(raw) == "final answer"

    def test_content_dict_empty_text(self):
        raw = _sse_lines({"content": {"text": ""}})
        assert _make_client()._parse_sse_response(raw) == ""

    def test_content_string(self):
        raw = _sse_lines({"content": "plain text"})
        assert _make_client()._parse_sse_response(raw) == "plain text"

    def test_content_empty_string_skipped(self):
        raw = _sse_lines({"content": ""})
        assert _make_client()._parse_sse_response(raw) == ""


# ---------------------------------------------------------------------------
# _parse_sse_response  --  Edge cases
# ---------------------------------------------------------------------------

class TestParseSSEEdgeCases:
    def test_empty_input(self):
        assert _make_client()._parse_sse_response("") == ""

    def test_no_data_prefix(self):
        """Lines without 'data:' prefix are ignored."""
        raw = "event: message\nid: 123\nretry: 5000\n"
        assert _make_client()._parse_sse_response(raw) == ""

    def test_done_stops_parsing(self):
        raw = (
            'data: {"content_delta": "before"}\n'
            "data: [DONE]\n"
            'data: {"content_delta": "after"}\n'
        )
        assert _make_client()._parse_sse_response(raw) == "before"

    def test_invalid_json_lines_skipped(self):
        raw = (
            "data: NOT_JSON\n"
            'data: {"content_delta": "ok"}\n'
            "data: {broken\n"
            "data: [DONE]\n"
        )
        assert _make_client()._parse_sse_response(raw) == "ok"

    def test_blank_lines_between_events(self):
        raw = (
            'data: {"content_delta": "a"}\n'
            "\n"
            "\n"
            'data: {"content_delta": "b"}\n'
            "data: [DONE]\n"
        )
        assert _make_client()._parse_sse_response(raw) == "ab"

    def test_data_with_extra_whitespace(self):
        raw = '  data:   {"content_delta": "x"}  \ndata: [DONE]\n'
        # Lines are stripped, so leading whitespace is handled
        assert _make_client()._parse_sse_response(raw) == "x"

    def test_no_done_marker(self):
        """Without [DONE], all data lines are parsed."""
        raw = _sse_lines(
            {"content_delta": "a"},
            {"content_delta": "b"},
            done=False,
        )
        assert _make_client()._parse_sse_response(raw) == "ab"

    def test_unknown_data_format_ignored(self):
        raw = _sse_lines({"some_other_field": "value"})
        assert _make_client()._parse_sse_response(raw) == ""

    def test_mixed_formats(self):
        """All three formats can coexist in a single stream."""
        raw = _sse_lines(
            {"content_delta": "A"},
            {"choices": [{"delta": {"content": "B"}}]},
            {"content": "C"},
        )
        assert _make_client()._parse_sse_response(raw) == "ABC"


# ---------------------------------------------------------------------------
# _headers
# ---------------------------------------------------------------------------

class TestHeaders:
    def test_headers_contain_auth(self):
        c = _make_client(api_key="my-secret-key")
        h = c._headers()
        assert h["Authorization"] == "my-secret-key"
        assert h["Content-Type"] == "application/json"
        assert h["Accept"] == "text/event-stream"


# ---------------------------------------------------------------------------
# _handle_tool_calls  --  parsing tool_calls from SSE
# ---------------------------------------------------------------------------

class TestHandleToolCalls:
    @pytest.mark.asyncio
    async def test_returns_empty_when_no_uuid(self):
        raw = _sse_lines({"tool_calls": [{"id": "tc1"}]})
        c = _make_client()
        client_mock = AsyncMock()
        result = await c._handle_tool_calls(client_mock, "http://url", "conv1", raw)
        assert result == ""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_tool_calls(self):
        raw = _sse_lines({"uuid": "asst-1", "role": "assistant"})
        c = _make_client()
        client_mock = AsyncMock()
        result = await c._handle_tool_calls(client_mock, "http://url", "conv1", raw)
        assert result == ""

    @pytest.mark.asyncio
    async def test_ignores_non_data_and_invalid_json_lines_while_parsing_tool_calls(self):
        raw = (
            "event: ping\n"
            "data: not-json\n"
            'data: {"uuid":"msg-1","role":"assistant"}\n'
            'data: {"tool_calls":[{"id":"tc-1"}]}\n'
            "data: [DONE]\n"
        )
        c = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = _sse_lines({"content": "done"})
        client_mock = AsyncMock()
        client_mock.post = AsyncMock(return_value=mock_response)

        result = await c._handle_tool_calls(client_mock, "http://url", "conv1", raw)

        assert result == "done"

    @pytest.mark.asyncio
    async def test_tool_calls_parser_ignores_non_data_lines_before_empty_result(self):
        raw = "event: ping\nid: 1\n"
        c = _make_client()
        client_mock = AsyncMock()
        result = await c._handle_tool_calls(client_mock, "http://url", "conv1", raw)
        assert result == ""

    @pytest.mark.asyncio
    async def test_acks_tool_calls_and_parses_continuation(self):
        """Full flow: parse tool_calls, ACK them, parse continuation."""
        raw_initial = _sse_lines(
            {"uuid": "msg-123", "role": "assistant", "tool_calls": [
                {"id": "tc-1", "function": {"name": "search_its"}},
                {"id": "tc-2", "function": {"name": "search_docs"}},
            ]},
        )

        continuation_sse = _sse_lines({"content_delta": "Result from tools"})

        c = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.text = continuation_sse

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await c._handle_tool_calls(
            mock_client, "http://example.com/messages", "conv-uuid", raw_initial
        )

        assert result == "Result from tools"

        # Verify ACK was sent correctly
        mock_client.post.assert_called_once()
        call_kwargs = mock_client.post.call_args
        body = call_kwargs.kwargs.get("json") or call_kwargs[1].get("json")
        assert body["parent_uuid"] == "msg-123"
        assert body["role"] == "tool"
        assert len(body["content"]) == 2
        assert body["content"][0]["tool_call_id"] == "tc-1"
        assert body["content"][0]["status"] == "accepted"
        assert body["content"][1]["tool_call_id"] == "tc-2"

    @pytest.mark.asyncio
    async def test_ack_failure_returns_error_message(self):
        raw_initial = _sse_lines(
            {"uuid": "msg-1", "role": "assistant", "tool_calls": [{"id": "tc-1"}]},
        )

        c = _make_client()
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_response)

        result = await c._handle_tool_calls(
            mock_client, "http://url", "conv1", raw_initial
        )
        assert "Tool ACK failed: 500" in result


# ---------------------------------------------------------------------------
# search()  --  integration with mocked httpx
# ---------------------------------------------------------------------------

class TestSearch:
    @pytest.mark.asyncio
    async def test_no_api_key(self):
        c = _make_client(api_key="")
        result = await c.search("test query")
        assert "ERROR" in result
        assert "NAPARNIK_API_KEY" in result

    @pytest.mark.asyncio
    async def test_conversation_creation_failure(self):
        c = _make_client()
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.text = "Forbidden"

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("test")
            assert "ERROR" in result
            assert "403" in result

    @pytest.mark.asyncio
    async def test_no_uuid_in_conversation_response(self):
        c = _make_client()
        conv_resp = MagicMock()
        conv_resp.status_code = 200
        conv_resp.json.return_value = {"id": 1}  # no uuid

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=conv_resp)
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("test")
            assert "ERROR" in result
            assert "UUID" in result

    @pytest.mark.asyncio
    async def test_message_send_failure(self):
        c = _make_client()
        conv_resp = MagicMock()
        conv_resp.status_code = 200
        conv_resp.json.return_value = {"uuid": "conv-123"}

        msg_resp = MagicMock()
        msg_resp.status_code = 500
        msg_resp.text = "Internal Server Error"

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[conv_resp, msg_resp])
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("test")
            assert "ERROR" in result
            assert "500" in result

    @pytest.mark.asyncio
    async def test_successful_search_with_text_response(self):
        c = _make_client()
        conv_resp = MagicMock()
        conv_resp.status_code = 200
        conv_resp.json.return_value = {"uuid": "conv-abc"}

        sse_body = _sse_lines(
            {"content_delta": "Answer "},
            {"content_delta": "from Naparnik"},
        )
        msg_resp = MagicMock()
        msg_resp.status_code = 200
        msg_resp.text = sse_body

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[conv_resp, msg_resp])
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("What is 1C?")
            assert result == "Answer from Naparnik"

    @pytest.mark.asyncio
    async def test_thinking_tags_stripped(self):
        c = _make_client()
        conv_resp = MagicMock()
        conv_resp.status_code = 200
        conv_resp.json.return_value = {"uuid": "conv-1"}

        sse_body = _sse_lines(
            {"content_delta": "<thinking>internal thoughts</thinking>"},
            {"content_delta": "Visible answer"},
        )
        msg_resp = MagicMock()
        msg_resp.status_code = 200
        msg_resp.text = sse_body

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[conv_resp, msg_resp])
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("q")
            assert "internal thoughts" not in result
            assert "Visible answer" in result

    @pytest.mark.asyncio
    async def test_think_tags_stripped(self):
        """Both <think> and <thinking> variants are removed."""
        c = _make_client()
        conv_resp = MagicMock()
        conv_resp.status_code = 200
        conv_resp.json.return_value = {"uuid": "conv-1"}

        sse_body = _sse_lines(
            {"content_delta": "<think>step by step</think>The answer is 42"},
        )
        msg_resp = MagicMock()
        msg_resp.status_code = 200
        msg_resp.text = sse_body

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[conv_resp, msg_resp])
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("q")
            assert result == "The answer is 42"

    @pytest.mark.asyncio
    async def test_empty_response_returns_fallback(self):
        c = _make_client()
        conv_resp = MagicMock()
        conv_resp.status_code = 200
        conv_resp.json.return_value = {"uuid": "conv-1"}

        sse_body = _sse_lines({"some_unknown": "data"})
        msg_resp = MagicMock()
        msg_resp.status_code = 200
        msg_resp.text = sse_body

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[conv_resp, msg_resp])
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("q")
            assert result == "No response from 1C:Naparnik."

    @pytest.mark.asyncio
    async def test_timeout_error(self):
        import httpx

        c = _make_client()

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=httpx.TimeoutException("timed out"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("q", timeout=5)
            assert "ERROR" in result
            assert "timed out" in result

    @pytest.mark.asyncio
    async def test_generic_exception(self):
        c = _make_client()

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=RuntimeError("connection reset"))
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("q")
            assert "ERROR" in result
            assert "connection reset" in result

    @pytest.mark.asyncio
    async def test_tool_calls_flow(self):
        """When initial response has tool_calls and empty text, tool ACK flow is triggered."""
        c = _make_client()
        conv_resp = MagicMock()
        conv_resp.status_code = 200
        conv_resp.json.return_value = {"uuid": "conv-1"}

        # Initial response contains tool_calls but no visible text
        initial_sse = _sse_lines(
            {"uuid": "asst-1", "role": "assistant", "tool_calls": [
                {"id": "tc-1", "function": {"name": "its_search"}},
            ]},
        )
        msg_resp = MagicMock()
        msg_resp.status_code = 200
        msg_resp.text = initial_sse

        # Continuation after ACK
        continuation_sse = _sse_lines({"content_delta": "Tool result text"})
        ack_resp = MagicMock()
        ack_resp.status_code = 200
        ack_resp.text = continuation_sse

        with patch("gateway.naparnik_client.httpx.AsyncClient") as MockClient:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(side_effect=[conv_resp, msg_resp, ack_resp])
            MockClient.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            MockClient.return_value.__aexit__ = AsyncMock(return_value=False)

            result = await c.search("search ITS")
            assert result == "Tool result text"
