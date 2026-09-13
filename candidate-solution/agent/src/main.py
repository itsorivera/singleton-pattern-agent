"""GeoAI analyzer agent - FastAPI service.

Receives transactions on POST /transactions, enriches them via the MCP server,
analyzes sentiment/urgency with an LLM (AWS Bedrock via LangChain, or a
heuristic fallback) and persists the interaction in PostgreSQL (Bronze layer).
"""

import asyncio
import logging
import time
from contextlib import asynccontextmanager
from typing import Any, Optional

import httpx
from fastapi import FastAPI
from pydantic import BaseModel, Field

from config import settings
from db import TransactionRepository
from llm import TransactionAnalyzer, build_bedrock_llm
from mcp_client import LocationMCPClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Transaction(BaseModel):
    transaction_id: str
    user_id: str
    timestamp: str
    query: str
    llm_model: Optional[str] = None
    tokens_used: Optional[int] = None
    response_time_ms: Optional[int] = None
    location_metadata: dict[str, Any] = Field(default_factory=dict)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.mcp = LocationMCPClient(settings.mcp_server_url)
    app.state.analyzer = TransactionAnalyzer(build_bedrock_llm())
    app.state.repo = TransactionRepository(settings.database_url)
    logger.info(
        "Analyzer agent ready (llm_mode=%s)",
        "bedrock" if app.state.analyzer.llm is not None else "heuristic-fallback",
    )
    yield


app = FastAPI(
    title="GeoAI Analyzer Agent",
    description="Recovered query processing agent for GeoAI Analytics",
    version="1.0.0",
    lifespan=lifespan,
)


@app.get("/")
async def root():
    return {
        "service": "GeoAI Analyzer Agent",
        "status": "running",
        "llm_mode": "bedrock" if app.state.analyzer.llm is not None else "heuristic-fallback",
    }


async def enrich_location(state, tx: Transaction) -> dict:
    meta = tx.location_metadata or {}
    latitude = meta.get("latitude")
    longitude = meta.get("longitude")
    city = meta.get("city")

    try:
        if latitude is not None and longitude is not None:
            return await state.mcp.get_location_by_coordinates(float(latitude), float(longitude))
        if city:
            return await state.mcp.get_location_by_city(str(city))
    except Exception as exc:
        logger.warning("MCP enrichment failed (%s); falling back to Location Service", exc)

    try:
        async with httpx.AsyncClient(
            base_url=settings.location_service_url, timeout=10.0
        ) as client:
            if latitude is not None and longitude is not None:
                resp = await client.get(
                    "/locations/by-coordinates",
                    params={"latitude": latitude, "longitude": longitude},
                )
            elif city:
                resp = await client.get(f"/locations/by-city/{city}")
            else:
                return {}
            if resp.status_code == 200:
                return resp.json()
    except Exception as exc:
        logger.warning("Location Service fallback failed (%s)", exc)
    return {}


@app.post("/transactions", status_code=201)
async def process_transaction(tx: Transaction):
    started = time.perf_counter()

    location = await enrich_location(app.state, tx)
    analysis = await asyncio.to_thread(app.state.analyzer.analyze, tx.query, location)
    interaction_id = app.state.repo.insert_bronze(tx, analysis)

    process_ms = round((time.perf_counter() - started) * 1000, 2)
    return {
        "status": "processed",
        "transaction_id": tx.transaction_id,
        "interaction_id": interaction_id,
        "sentiment": analysis["sentiment"],
        "urgency_level": analysis["urgency_level"],
        "location": (
            {"city": location.get("city"), "country": location.get("country")}
            if location
            else None
        ),
        "processed_ms": process_ms,
        "agent_response": analysis["agent_response"],
    }


def main() -> None:
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=settings.agent_port)


if __name__ == "__main__":
    main()