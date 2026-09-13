"""Cliente MCP de prueba para validar el MCP Server de ubicaciones.

Uso (desde la raíz del repositorio):
    uv run python candidate-solution/mcp_server/test_client.py
"""

import asyncio
import json

from mcp import ClientSession
from mcp.client.sse import sse_client

URL = "http://localhost:8003/sse"


async def main() -> None:
    async with sse_client(URL) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            tools = await session.list_tools()
            print("Herramientas disponibles:", [t.name for t in tools.tools])
            print()

            result = await session.call_tool(
                "get_location_by_coordinates",
                {"latitude": 19.4326, "longitude": -99.1332},
            )
            print("get_location_by_coordinates(19.4326, -99.1332):")
            print(json.dumps(json.loads(result.content[0].text), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())