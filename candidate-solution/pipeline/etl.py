"""Pipeline ETL: Bronze -> Silver -> Gold transformations with pandas.

Reads rows from agent_interactions (Bronze) that have not yet been promoted,
enriches them with location context via the Location Service, validates them
into enriched_transactions (Silver) and recomputes pre-aggregated metrics into
analytics_metrics (Gold). Run with:

    PYTHONPATH=candidate-solution/pipeline uv run python -m etl

Or in watch mode (repeated incremental runs) for real-time Gold updates:

    PYTHONPATH=candidate-solution/pipeline uv run python -m etl --watch 30
"""

import argparse
import json
import logging
import math
import time
from typing import Any

import httpx
import pandas as pd
import psycopg2
from config import database_url, location_service_url
from psycopg2.extras import execute_batch

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger("etl")

BRONZE_SELECT_SQL = """
SELECT ai.interaction_id, ai.user_id, ai.timestamp, ai.user_query,
       ai.sentiment, ai.urgency_level, ai.raw_metadata,
       ai.tokens_used, ai.response_time_ms
FROM agent_interactions ai
LEFT JOIN enriched_transactions et ON et.interaction_id = ai.interaction_id
WHERE et.interaction_id IS NULL
ORDER BY ai.timestamp
"""

SILVER_INSERT_SQL = """
INSERT INTO enriched_transactions (
    interaction_id, user_id, timestamp, city, country, latitude, longitude,
    timezone, weather_condition, temperature, humidity, wind_speed,
    observations, population, language, currency, is_valid, validation_errors
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

GOLD_SOURCE_SQL = """
SELECT et.city AS city, et.country AS country, et.timestamp AS timestamp,
       ai.user_id, ai.sentiment, ai.urgency_level, ai.tokens_used,
       ai.response_time_ms, ai.user_query, et.temperature, et.weather_condition
FROM enriched_transactions et
JOIN agent_interactions ai ON et.interaction_id = ai.interaction_id
ORDER BY et.timestamp
"""

GOLD_UPSERT_SQL = """
INSERT INTO analytics_metrics (
    metric_date, city, country, total_transactions, avg_response_time_ms,
    total_tokens_used, unique_users, most_common_query_type, peak_hour,
    avg_temperature, most_common_weather,
    positive_sentiment_count, neutral_sentiment_count, negative_sentiment_count,
    high_urgency_count, medium_urgency_count, low_urgency_count
) VALUES (
    %(metric_date)s, %(city)s, %(country)s, %(total_transactions)s,
    %(avg_response_time_ms)s, %(total_tokens_used)s, %(unique_users)s,
    %(most_common_query_type)s, %(peak_hour)s, %(avg_temperature)s,
    %(most_common_weather)s, %(positive_sentiment_count)s,
    %(neutral_sentiment_count)s, %(negative_sentiment_count)s,
    %(high_urgency_count)s, %(medium_urgency_count)s, %(low_urgency_count)s
)
ON CONFLICT (metric_date, city) DO UPDATE SET
    country = EXCLUDED.country,
    total_transactions = EXCLUDED.total_transactions,
    avg_response_time_ms = EXCLUDED.avg_response_time_ms,
    total_tokens_used = EXCLUDED.total_tokens_used,
    unique_users = EXCLUDED.unique_users,
    most_common_query_type = EXCLUDED.most_common_query_type,
    peak_hour = EXCLUDED.peak_hour,
    avg_temperature = EXCLUDED.avg_temperature,
    most_common_weather = EXCLUDED.most_common_weather,
    positive_sentiment_count = EXCLUDED.positive_sentiment_count,
    neutral_sentiment_count = EXCLUDED.neutral_sentiment_count,
    negative_sentiment_count = EXCLUDED.negative_sentiment_count,
    high_urgency_count = EXCLUDED.high_urgency_count,
    medium_urgency_count = EXCLUDED.medium_urgency_count,
    low_urgency_count = EXCLUDED.low_urgency_count,
    aggregated_at = NOW()
"""


def _parse_json(value: Any) -> dict:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return {}
    return value or {}


def _to_rows(df: pd.DataFrame) -> list[dict]:
    rows: list[dict] = []
    for record in df.to_dict("records"):
        row: dict = {}
        for key, value in record.items():
            if isinstance(value, float) and math.isnan(value):
                row[key] = None
            elif isinstance(value, pd.Timestamp):
                row[key] = value.to_pydatetime()
            elif hasattr(value, "item"):
                row[key] = value.item()
            else:
                row[key] = value
        rows.append(row)
    return rows


def fetch(conn, sql: str) -> list[dict]:
    with conn.cursor() as cur:
        cur.execute(sql)
        columns = [d[0] for d in cur.description] if cur.description else []
        return [dict(zip(columns, row)) for row in cur.fetchall()]


def enrich_location(metadata: dict | None) -> dict | None:
    metadata = _parse_json(metadata)
    if not metadata:
        return None
    latitude = metadata.get("latitude")
    longitude = metadata.get("longitude")
    city = metadata.get("city")
    try:
        if latitude is not None and longitude is not None:
            response = httpx.get(
                f"{location_service_url}/locations/by-coordinates",
                params={"latitude": latitude, "longitude": longitude},
                timeout=10.0,
            )
            if response.status_code == 200:
                return response.json()
        if city:
            response = httpx.get(f"{location_service_url}/locations/by-city/{city}", timeout=10.0)
            if response.status_code == 200:
                return response.json()
    except httpx.HTTPError as exc:
        logger.warning("Location enrichment failed: %s", exc)
    return None


def _validate_location(location: dict | None) -> tuple[bool, list]:
    errors: list = []
    if not location:
        return False, ["location enrichment failed"]
    weather = location.get("weather") or {}
    temperature = weather.get("temperature")
    if temperature is not None and not -50.0 <= float(temperature) <= 60.0:
        errors.append("temperature out of range")
    humidity = weather.get("humidity")
    if humidity is not None and not 0 <= float(humidity) <= 100:
        errors.append("humidity out of range")
    latitude = location.get("latitude")
    if latitude is not None and not -90.0 <= float(latitude) <= 90.0:
        errors.append("latitude out of range")
    longitude = location.get("longitude")
    if longitude is not None and not -180.0 <= float(longitude) <= 180.0:
        errors.append("longitude out of range")
    return (not errors), errors


def build_silver_rows(bronze_rows: list[dict]) -> list[dict]:
    if not bronze_rows:
        return []
    df = pd.DataFrame(bronze_rows)
    df["location"] = df["raw_metadata"].apply(enrich_location)
    df["city"] = df["location"].apply(lambda loc: (loc or {}).get("city"))
    df["country"] = df["location"].apply(lambda loc: (loc or {}).get("country"))
    df["latitude"] = df["location"].apply(lambda loc: (loc or {}).get("latitude"))
    df["longitude"] = df["location"].apply(lambda loc: (loc or {}).get("longitude"))
    df["timezone"] = df["location"].apply(lambda loc: (loc or {}).get("timezone"))
    df["weather_condition"] = df["location"].apply(
        lambda loc: ((loc or {}).get("weather") or {}).get("condition")
    )
    df["temperature"] = df["location"].apply(
        lambda loc: ((loc or {}).get("weather") or {}).get("temperature")
    )
    df["humidity"] = df["location"].apply(
        lambda loc: ((loc or {}).get("weather") or {}).get("humidity")
    )
    df["wind_speed"] = df["location"].apply(
        lambda loc: ((loc or {}).get("weather") or {}).get("wind_speed")
    )
    df["observations"] = df["location"].apply(lambda loc: (loc or {}).get("observations") or [])
    df["population"] = df["location"].apply(
        lambda loc: ((loc or {}).get("demographics") or {}).get("population")
    )
    df["language"] = df["location"].apply(
        lambda loc: ((loc or {}).get("demographics") or {}).get("language")
    )
    df["currency"] = df["location"].apply(
        lambda loc: ((loc or {}).get("demographics") or {}).get("currency")
    )
    df["validation"] = df["location"].apply(_validate_location)
    df["is_valid"] = df["validation"].apply(lambda v: v[0])
    df["validation_errors"] = df["validation"].apply(lambda v: v[1])
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return _to_rows(df)


def insert_silver(conn, rows: list[dict]) -> int:
    if not rows:
        return 0
    values = [
        (
            r["interaction_id"],
            r["user_id"],
            r["timestamp"],
            r["city"],
            r["country"],
            r["latitude"],
            r["longitude"],
            r["timezone"],
            r["weather_condition"],
            r["temperature"],
            r["humidity"],
            r["wind_speed"],
            r["observations"],
            r["population"],
            r["language"],
            r["currency"],
            r["is_valid"],
            r["validation_errors"],
        )
        for r in rows
    ]
    with conn.cursor() as cur:
        execute_batch(cur, SILVER_INSERT_SQL, values, page_size=100)
    conn.commit()
    return len(values)


def classify_query_type(query: Any) -> str:
    q = str(query or "").lower()
    if any(w in q for w in ("horas pico", "peak hour")):
        return "peak_hours"
    if any(
        w in q
        for w in (
            "clima",
            "weather",
            "temperatur",
            "temperature",
            "humeda",
            "humidity",
            "lluvia",
            "rain",
            "condiciones",
            "conditions",
        )
    ):
        return "weather"
    if any(
        w in q
        for w in (
            "poblaci",
            "population",
            "demograf",
            "demographics",
            "habitante",
            "inhabitant",
        )
    ):
        return "demographics"
    if any(w in q for w in ("zona horaria", "timezone", "hora", "time")):
        return "time"
    return "general"


def _gold_group(g: pd.DataFrame) -> pd.Series:
    sentiment = g["sentiment"].dropna().str.lower().value_counts()
    urgency = g["urgency_level"].dropna().str.lower().value_counts()
    peak_hour = g["hour"].value_counts()
    question_type = g["query_type"].value_counts()
    weather = g["weather_condition"].dropna()
    has_response_time = g["response_time_ms"].notna().any()
    has_tokens = g["tokens_used"].notna().any()
    has_temperature = g["temperature"].notna().any()
    return pd.Series(
        {
            "country": g["country"].iloc[0],
            "total_transactions": len(g),
            "avg_response_time_ms": (
                round(float(g["response_time_ms"].mean()), 2) if has_response_time else None
            ),
            "total_tokens_used": int(g["tokens_used"].sum()) if has_tokens else 0,
            "unique_users": int(g["user_id"].nunique()),
            "most_common_query_type": (
                str(question_type.idxmax()) if not question_type.empty else "general"
            ),
            "peak_hour": int(peak_hour.idxmax()) if not peak_hour.empty else 0,
            "avg_temperature": (
                round(float(g["temperature"].mean()), 2) if has_temperature else None
            ),
            "most_common_weather": (str(weather.mode().iloc[0]) if not weather.empty else None),
            "positive_sentiment_count": int(sentiment.get("positive", 0)),
            "neutral_sentiment_count": int(sentiment.get("neutral", 0)),
            "negative_sentiment_count": int(sentiment.get("negative", 0)),
            "high_urgency_count": int(urgency.get("high", 0)),
            "medium_urgency_count": int(urgency.get("medium", 0)),
            "low_urgency_count": int(urgency.get("low", 0)),
        }
    )


def build_gold(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame()
    df = df.copy()
    df["city"] = df["city"].fillna("Desconocido").replace("", "Desconocido")
    df["country"] = df["country"].fillna("No identificado")
    df["metric_date"] = pd.to_datetime(df["timestamp"]).dt.date
    df["hour"] = pd.to_datetime(df["timestamp"]).dt.hour
    df["query_type"] = df["user_query"].apply(classify_query_type)
    grouped = df.groupby(["metric_date", "city"], dropna=False)
    return grouped.apply(_gold_group, include_groups=False).reset_index()


def upsert_gold(conn, gold_records: list[dict]) -> int:
    if not gold_records:
        return 0
    with conn.cursor() as cur:
        execute_batch(cur, GOLD_UPSERT_SQL, gold_records, page_size=100)
    conn.commit()
    return len(gold_records)


def _load_gold_source(conn) -> pd.DataFrame:
    rows = fetch(conn, GOLD_SOURCE_SQL)
    if not rows:
        return pd.DataFrame()
    return pd.DataFrame(rows)


def run_etl(limit: int | None = None) -> dict:
    conn = psycopg2.connect(database_url)
    try:
        bronze_sql = BRONZE_SELECT_SQL
        if limit:
            bronze_sql = f"{bronze_sql}\nLIMIT {int(limit)}"
        bronze_rows = fetch(conn, bronze_sql)
        silver_inserted = insert_silver(conn, build_silver_rows(bronze_rows))

        gold_records = build_gold(_load_gold_source(conn))
        gold_upserted = upsert_gold(conn, _to_rows(gold_records))

        return {
            "bronze_processed": len(bronze_rows),
            "silver_inserted": silver_inserted,
            "gold_upserted": gold_upserted,
        }
    finally:
        conn.close()


def watch(interval: int, limit: int | None = None) -> None:
    logger.info("ETL watch mode enabled (interval=%ss)", interval)
    while True:
        try:
            summary = run_etl(limit=limit)
            logger.info("ETL run complete: %s", summary)
        except Exception:
            logger.exception("ETL run failed")
        time.sleep(interval)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Execute pipeline ETL (Bronze -> Silver -> Gold).")
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of bronze rows to process.",
    )
    parser.add_argument(
        "--watch",
        type=int,
        default=0,
        help="Run continuously every N seconds.",
    )
    args = parser.parse_args(argv)
    if args.watch and args.watch > 0:
        watch(args.watch, args.limit)
    else:
        logger.info("ETL run: %s", run_etl(limit=args.limit))


if __name__ == "__main__":
    main()
