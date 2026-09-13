"""GeoAI Analytics dashboard - Streamlit app reading Silver and Gold layers.

Shows real-time KPIs and analytical charts built on top of the Gold layer
(analytics_metrics), plus the latest enriched transactions. The metrics
section auto-refreshes at a configurable interval. Run with:

    PYTHONPATH=candidate-solution/dashboard uv run streamlit run candidate-solution/dashboard/app.py
"""

import pandas as pd
import psycopg2
import streamlit as st
from config import database_url

st.set_page_config(page_title="GeoAI Analytics", page_icon=":earth_americas:", layout="wide")

GOLD_SQL = """
SELECT metric_date, city, country, total_transactions, avg_response_time_ms,
       total_tokens_used, unique_users, most_common_query_type, peak_hour,
       avg_temperature, most_common_weather,
       positive_sentiment_count, neutral_sentiment_count, negative_sentiment_count,
       high_urgency_count, medium_urgency_count, low_urgency_count, aggregated_at
FROM analytics_metrics
"""


def _fetch(sql: str) -> pd.DataFrame:
    try:
        conn = psycopg2.connect(database_url, connect_timeout=5)
    except psycopg2.Error as exc:
        st.error(f"No se pudo conectar a PostgreSQL: {exc}")
        return pd.DataFrame()
    try:
        with conn.cursor() as cur:
            cur.execute(sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchall()
        return pd.DataFrame(rows, columns=columns)
    except psycopg2.Error as exc:
        st.error(f"Error consultando la base de datos: {exc}")
        return pd.DataFrame()
    finally:
        conn.close()


st.title("GeoAI Analytics - Métricas en tiempo real")
st.caption("KPIs y gráficos construidos sobre la capa Gold (analytics_metrics).")

interval = st.sidebar.selectbox(
    "Frecuencia de actualización",
    options=[5, 10, 15, 30, 60],
    index=1,
    format_func=lambda s: f"{s} s",
)

st.sidebar.markdown(
    "El pipeline ETL (`python -m etl`) promueve datos de Bronze a Gold "
    "periódicamente para alimentar este dashboard."
)


@st.fragment(run_every=interval)
def render_dashboard():
    gold = _fetch(GOLD_SQL)
    if gold.empty:
        st.info("Todavía no hay métricas en la capa Gold. Ejecuta el pipeline ETL primero.")
        return

    totals = gold.agg(
        {
            "total_transactions": "sum",
            "unique_users": "sum",
            "total_tokens_used": "sum",
            "avg_response_time_ms": "mean",
        }
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transacciones", f"{int(totals['total_transactions']):,}")
    c2.metric("Usuarios únicos", f"{int(totals['unique_users']):,}")
    c3.metric("Tokens usados", f"{int(totals['total_tokens_used']):,}")
    c4.metric(
        "Tiempo de respuesta promedio",
        (
            f"{totals['avg_response_time_ms']:,.0f} ms"
            if pd.notna(totals["avg_response_time_ms"])
            else "—"
        ),
    )

    st.subheader("Sentimiento de consultas")
    st.bar_chart(
        pd.DataFrame(
            {
                "Transacciones": [
                    int(gold["positive_sentiment_count"].sum()),
                    int(gold["neutral_sentiment_count"].sum()),
                    int(gold["negative_sentiment_count"].sum()),
                ]
            },
            index=["Positivas", "Neutras", "Negativas"],
        )
    )

    st.subheader("Nivel de urgencia")
    st.bar_chart(
        pd.DataFrame(
            {
                "Transacciones": [
                    int(gold["high_urgency_count"].sum()),
                    int(gold["medium_urgency_count"].sum()),
                    int(gold["low_urgency_count"].sum()),
                ]
            },
            index=["Alta", "Media", "Baja"],
        )
    )

    col_a, col_b = st.columns(2)
    with col_a:
        st.subheader("Transacciones por ciudad")
        by_city = gold.groupby("city")["total_transactions"].sum().sort_values(ascending=False)
        st.bar_chart(by_city)
    with col_b:
        st.subheader("Transacciones por día")
        by_day = gold.groupby("metric_date")["total_transactions"].sum().sort_index()
        st.line_chart(by_day)

    col_c, col_d = st.columns(2)
    with col_c:
        st.subheader("Tiempo de respuesta promedio por día")
        response_by_day = gold.groupby("metric_date")["avg_response_time_ms"].mean().sort_index()
        st.line_chart(response_by_day)
    with col_d:
        st.subheader("Temperatura promedio por ciudad")
        silver = _fetch("SELECT city, temperature FROM enriched_transactions WHERE is_valid = TRUE")
        if not silver.empty:
            temp_by_city = silver.groupby("city")["temperature"].mean().sort_values(ascending=False)
            st.bar_chart(temp_by_city)

    st.subheader("Últimas transacciones enriquecidas")
    latest = _fetch("SELECT * FROM v_recent_enriched_transactions LIMIT 20")
    if not latest.empty:
        st.dataframe(latest, width="stretch")

    last_agg = gold["aggregated_at"].max()
    st.caption(f"Última agregación Gold registrada: {last_agg}")


render_dashboard()
