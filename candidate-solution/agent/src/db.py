"""Persistence of agent interactions (Bronze layer: agent_interactions)."""

import json
import logging

import psycopg2

logger = logging.getLogger(__name__)

INSERT_BRONZE_SQL = """
INSERT INTO agent_interactions (
    transaction_id, user_id, timestamp, user_query, agent_response,
    llm_model, tokens_used, response_time_ms, sentiment, urgency_level, raw_metadata
) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
RETURNING interaction_id
"""


class TransactionRepository:
    def __init__(self, database_url: str):
        self.database_url = database_url

    def insert_bronze(self, transaction, analysis: dict) -> str:
        conn = psycopg2.connect(self.database_url)
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    INSERT_BRONZE_SQL,
                    (
                        transaction.transaction_id,
                        transaction.user_id,
                        transaction.timestamp,
                        transaction.query,
                        analysis.get("agent_response"),
                        analysis.get("llm_model"),
                        analysis.get("tokens_used"),
                        transaction.response_time_ms,
                        analysis.get("sentiment"),
                        analysis.get("urgency_level"),
                        json.dumps(transaction.location_metadata, ensure_ascii=False),
                    ),
                )
                interaction_id = cursor.fetchone()[0]
            conn.commit()
            return str(interaction_id)
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
