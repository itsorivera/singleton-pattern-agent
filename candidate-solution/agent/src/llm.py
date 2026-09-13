"""Sentiment and urgency analysis using LLM (AWS Bedrock via LangChain) with fallback."""

import json
import logging
import re
from typing import Optional

import boto3
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from config import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an operations analyst for GeoAI Analytics, a location-context AI company. "
    "You receive a user query and its enriched location context (weather, demographics, "
    "observations). Analyze the message and return ONLY a JSON object with exactly these keys:\n"
    '- "sentiment": "positive", "neutral" or "negative"\n'
    '- "urgency_level": "low", "medium" or "high"\n'
    '- "agent_response": a concise natural language answer to the user query, in the same '
    "language as the query, using the location context.\n"
    "Do not add explanations or markdown."
)

URGENCY_HIGH = ("urgente", "urgent", "emergency", "asap", "immediately", "inmediato", "critical", "crítico")
URGENCY_MEDIUM = ("cuando", "cuándo", "when", "hora", "time", "today", "hoy", "tomorrow", "mañana", "donde", "dónde", "where", "cómo", "how", "información", "information")
NEGATIVE_WORDS = ("lluvia", "rain", "tormenta", "storm", "mal", "bad", "problema", "problem", "error", "failed", "queja", "complaint", "no funciona", "broken")
POSITIVE_WORDS = ("genial", "great", "bien", "good", "excelente", "excellent", "me gusta", "love", "awesome")

ALLOWED_SENTIMENT = ("positive", "neutral", "negative")
ALLOWED_URGENCY = ("low", "medium", "high")


def build_bedrock_llm():
    if not (settings.aws_access_key_id and settings.aws_secret_access_key):
        logger.info("AWS credentials not configured; heuristic fallback will be used")
        return None
    try:
        from langchain_aws import ChatBedrockConverse

        session = boto3.Session(
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.aws_region
        )
        client = session.client('bedrock-runtime')
        logger.info(
            "Using AWS Bedrock model %s (region %s)", settings.bedrock_model_id, settings.aws_region
        )
        return ChatBedrockConverse(
            client=client,
            model_id=settings.bedrock_model_id,
            region_name=settings.aws_region,
            temperature=0.1,
            max_tokens=512,
        )
    except Exception as exc:
        logger.warning("Could not initialize Bedrock LLM: %s", exc)
        return None


class TransactionAnalyzer:
    def __init__(self, llm=None):
        self.llm = llm
        if llm is not None:
            self.chain = (
                ChatPromptTemplate.from_messages(
                    [
                        ("system", SYSTEM_PROMPT),
                        ("user", "User query: {query}\n\nLocation context: {location}"),
                    ]
                )
                | llm
                | StrOutputParser()
            )

    def analyze(self, query: str, location: Optional[dict]) -> dict:
        if self.llm is None:
            return self._fallback(query, location)
        try:
            raw = self.chain.invoke(
                {
                    "query": query,
                    "location": json.dumps(location or {}, ensure_ascii=False),
                }
            )
            return self._normalize(self._parse_json(raw), query, location)
        except Exception as exc:
            logger.warning("LLM analysis failed (%s); using heuristic fallback", exc)
            return self._fallback(query, location)

    def _parse_json(self, raw: str) -> dict:
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw.strip())
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group(0))
            raise ValueError(f"Could not parse JSON from LLM output: {raw[:200]}")

    def _normalize(self, data: dict, query: str, location: Optional[dict]) -> dict:
        fallback = self._fallback(query, location)
        sentiment = str(data.get("sentiment", "")).strip().lower()
        urgency = str(data.get("urgency_level", "")).strip().lower()
        response = str(data.get("agent_response", "")).strip()
        return {
            "sentiment": sentiment if sentiment in ALLOWED_SENTIMENT else fallback["sentiment"],
            "urgency_level": urgency if urgency in ALLOWED_URGENCY else fallback["urgency_level"],
            "agent_response": response or fallback["agent_response"],
        }

    def _fallback(self, query: str, location: Optional[dict]) -> dict:
        q = query.lower()
        urgency = (
            "high"
            if any(word in q for word in URGENCY_HIGH)
            else "medium"
            if any(word in q for word in URGENCY_MEDIUM)
            else "low"
        )
        sentiment = (
            "positive"
            if any(word in q for word in POSITIVE_WORDS)
            else "negative"
            if any(word in q for word in NEGATIVE_WORDS)
            else "neutral"
        )

        info = location or {}
        weather = info.get("weather") or {}
        demographics = info.get("demographics") or {}
        city = info.get("city") or "tu ubicación"
        parts = [f"Ubicación: {city}."]
        if weather.get("temperature") is not None:
            parts.append(f"Temperatura: {weather['temperature']}°C.")
        if weather.get("condition"):
            parts.append(f"Clima: {weather['condition']}.")
        if demographics.get("population") is not None:
            parts.append(f"Población: {demographics['population']}.")
        response = " ".join(parts) + f" Consulta: {query}"

        return {
            "sentiment": sentiment,
            "urgency_level": urgency,
            "agent_response": response,
        }