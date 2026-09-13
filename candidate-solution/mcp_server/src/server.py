"""MCP Server for the GeoAI Location Service (provided on port 8001).

Exposes the Location Service REST endpoints as MCP tools over SSE so the
analyzer agent (and any MCP client) can query contextual location data.
"""

import json
import logging

import httpx
from mcp.server.fastmcp import FastMCP

from config import settings

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "GeoAI Location MCP Server",
    instructions=(
        "Query contextual location data (weather, demographics, observations) "
        "from the GeoAI Location Service. Use coordinates or a city name to "
        "enrich transaction queries with location context."
    ),
)


async def _get(path: str, **params) -> dict:
    async with httpx.AsyncClient(
        base_url=settings.location_service_url, timeout=10.0
    ) as client:
        resp = await client.get(path, params=params or None)
        resp.raise_for_status()
        return resp.json()


def _ok(data) -> str:
    return json.dumps(data, ensure_ascii=False, default=str)


@mcp.tool()
async def list_locations() -> str:
    """List all available locations."""
    return _ok(await _get("/locations"))


@mcp.tool()
async def get_location_by_id(location_id: str) -> str:
    """Get location details by its id (e.g. loc_cdmx_001)."""
    return _ok(await _get(f"/locations/{location_id}"))


@mcp.tool()
async def get_location_by_city(city: str) -> str:
    """Get location details for a city name (case-insensitive)."""
    return _ok(await _get(f"/locations/by-city/{city}"))


@mcp.tool()
async def get_location_by_coordinates(
    latitude: float, longitude: float, tolerance: float = 0.5
) -> str:
    """Get the nearest location within tolerance of the given coordinates."""
    try:
        return _ok(
            await _get(
                "/locations/by-coordinates",
                latitude=latitude,
                longitude=longitude,
                tolerance=tolerance,
            )
        )
    except httpx.HTTPStatusError:
        logger.info(
            "by-coordinates endpoint unavailable; scanning location list for (%.4f, %.4f)",
            latitude,
            longitude,
        )
        return _ok(await _find_nearest(latitude, longitude, tolerance))


async def _find_nearest(latitude: float, longitude: float, tolerance: float) -> dict:
    locations = await _get("/locations")
    nearest = min(
        locations,
        key=lambda loc: abs(loc["latitude"] - latitude)
        + abs(loc["longitude"] - longitude),
    )
    if (
        abs(nearest["latitude"] - latitude) <= tolerance
        and abs(nearest["longitude"] - longitude) <= tolerance
    ):
        return nearest
    raise ValueError(
        f"No location within {tolerance} degrees of ({latitude}, {longitude})"
    )


@mcp.tool()
async def get_locations_by_country(country: str) -> str:
    """List all locations in a country (case-insensitive)."""
    return _ok(await _get(f"/locations/by-country/{country}"))


def main() -> None:
    logging.basicConfig(level=logging.INFO)
    mcp.settings.host = "0.0.0.0"
    mcp.settings.port = settings.mcp_server_port
    mcp.run(transport="sse")


if __name__ == "__main__":
    main()