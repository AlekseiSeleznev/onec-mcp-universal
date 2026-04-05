"""
Client for 1C:Napilnik (1C:Naparnik / 1C:Buddy) API.
Provides ITS documentation search via code.1c.ai chat API.
"""
from __future__ import annotations

import json
import logging
import re

import httpx

log = logging.getLogger(__name__)

BASE_URL = "https://code.1c.ai"
CONVERSATIONS_URL = f"{BASE_URL}/chat_api/v1/conversations/"


class NapilnikClient:
    """Stateless client for 1C:Napilnik search API."""

    def __init__(self, api_key: str) -> None:
        self._api_key = api_key

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": self._api_key,
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
        }

    async def search(self, query: str, timeout: int = 60) -> str:
        """Send a question to 1C:Napilnik and return the answer."""
        if not self._api_key:
            return "ERROR: NAPILNIK_API_KEY not configured. Set it in .env file."

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                # Step 1: Create conversation with custom skill (enables ITS search tools)
                conv_resp = await client.post(
                    CONVERSATIONS_URL,
                    headers=self._headers(),
                    json={
                        "skill_name": "raw",
                        "is_chat": True,
                        "ui_language": "russian",
                        "script_language": "ru",
                    },
                )
                if conv_resp.status_code != 200:
                    return f"ERROR: Failed to create conversation: {conv_resp.status_code} {conv_resp.text[:300]}"

                conv_data = conv_resp.json()
                conv_uuid = conv_data.get("uuid", "")
                if not conv_uuid:
                    return f"ERROR: No conversation UUID in response: {json.dumps(conv_data)[:300]}"

                # Step 2: Send message and collect SSE response
                msg_url = f"{CONVERSATIONS_URL}{conv_uuid}/messages"
                msg_resp = await client.post(
                    msg_url,
                    headers=self._headers(),
                    json={
                        "parent_uuid": None,
                        "role": "user",
                        "content": {
                            "content": {
                                "instruction": query,
                            }
                        },
                    },
                )

                if msg_resp.status_code != 200:
                    return f"ERROR: Failed to send message: {msg_resp.status_code} {msg_resp.text[:300]}"

                # Step 3: Parse SSE stream, collect text
                full_text = self._parse_sse_response(msg_resp.text)

                # Step 4: Handle tool calls — ACK them and get continuation
                # Check if the response contains tool_calls that need ACK
                if "tool_calls" in msg_resp.text and not full_text.strip():
                    full_text = await self._handle_tool_calls(
                        client, msg_url, conv_uuid, msg_resp.text
                    )

                # Clean up thinking tags
                full_text = re.sub(r'<think(?:ing)?>(.*?)</think(?:ing)?>', '', full_text, flags=re.DOTALL)
                return full_text.strip() if full_text.strip() else "No response from 1C:Napilnik."

        except httpx.TimeoutException:
            return f"ERROR: 1C:Napilnik request timed out after {timeout}s"
        except Exception as exc:
            return f"ERROR: 1C:Napilnik API error: {exc}"

    def _parse_sse_response(self, raw: str) -> str:
        """Extract text content from SSE stream."""
        chunks: list[str] = []
        for line in raw.split("\n"):
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            # Format 1: content_delta (can be str or {"content": "..."})
            cd = data.get("content_delta")
            if cd:
                if isinstance(cd, dict):
                    chunks.append(cd.get("content", ""))
                elif isinstance(cd, str):
                    chunks.append(cd)
            # Format 2: OpenAI-like choices
            elif "choices" in data:
                for choice in data.get("choices", []):
                    delta = choice.get("delta", {})
                    if delta and delta.get("content"):
                        chunks.append(delta["content"])
            # Format 3: Final content
            elif isinstance(data.get("content"), dict):
                text = data["content"].get("text", "")
                if text:
                    chunks.append(text)
            elif isinstance(data.get("content"), str) and data["content"]:
                chunks.append(data["content"])

        return "".join(str(c) for c in chunks if c)

    async def _handle_tool_calls(
        self, client: httpx.AsyncClient, msg_url: str, conv_uuid: str, raw_response: str
    ) -> str:
        """ACK tool calls and collect the final text response."""
        # Parse tool calls from SSE data
        assistant_uuid = None
        tool_calls = []

        for line in raw_response.split("\n"):
            line = line.strip()
            if not line.startswith("data:"):
                continue
            data_str = line[5:].strip()
            if data_str == "[DONE]":
                break
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                continue

            if "uuid" in data and data.get("role") == "assistant":
                assistant_uuid = data["uuid"]
            if "tool_calls" in data:
                tool_calls = data["tool_calls"]

        if not assistant_uuid or not tool_calls:
            return ""

        # ACK all tool calls
        ack_content = [
            {
                "tool_call_id": tc.get("id", ""),
                "status": "accepted",
                "content": None,
            }
            for tc in tool_calls
        ]

        ack_resp = await client.post(
            msg_url,
            headers=self._headers(),
            json={
                "parent_uuid": assistant_uuid,
                "role": "tool",
                "content": ack_content,
            },
        )

        if ack_resp.status_code != 200:
            return f"Tool ACK failed: {ack_resp.status_code}"

        # Collect the continuation response
        return self._parse_sse_response(ack_resp.text)
