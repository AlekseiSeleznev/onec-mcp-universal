"""Handler for ITS search tool via 1C:Naparnik."""

from __future__ import annotations

from ..naparnik_client import NaparnikClient


async def its_search(query: str, api_key: str) -> str:
    """Run ITS search using configured Naparnik API key."""
    if not api_key:
        return (
            "ERROR: NAPARNIK_API_KEY not configured.\n"
            "Get your API key at https://code.1c.ai (Profile → API token).\n"
            "Add to .env: NAPARNIK_API_KEY=your-key-here"
        )

    client = NaparnikClient(api_key)
    return await client.search(query)
