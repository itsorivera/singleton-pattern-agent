"""Minimal MCP client used by the agent to call Location MCP tools."""

import json
import logging
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client

logger = logging.getLogger(__name__)


class LocationMCPClient:
    def __init__(self, url: str):
        self.url = url

    async def call_tool(self, name: str, arguments: dict) -> dict[str, Any]:
        async with sse_client(self.url) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments=arguments)

        for content in result.content:
            block_type = getattr(content, "type", None)
            text = getattr(content, "text", None)
            if block_type == "text" and text:
                try:
                    return json.loads(text)
                except json.JSONDecodeError:
                    return {"text": text}
        return {}

    async def get_location_by_coordinates(
        self, latitude: float, longitude: float
    ) -> dict[str, Any]:
        return await self.call_tool(
            "get_location_by_coordinates",
            {"latitude": latitude, "longitude": longitude},
        )

    async def get_location_by_city(self, city: str) -> dict[str, Any]:
        return await self.call_tool("get_location_by_city", {"city": city})