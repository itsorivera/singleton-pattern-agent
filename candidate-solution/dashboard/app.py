"""GeoAI Analytics dashboard - Streamlit app reading ONLY the Gold layer.

All KPIs and analytical charts are built on top of analytics_metrics (Gold),
so the dashboard never queries Silver or Bronze directly. The metrics section
auto-refreshes at a configurable interval. Run with:

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
st.caption("KPIs y gráficos construidos únicamente sobre la capa Gold (analytics_metrics).")

interval = st.sidebar.selectbox(
    "Frecuencia de actualización",
    options=[5, 10, 15, 30, 60],
    index=1,
    format_func=lambda s: f"{s} s",
)

st.sidebar.markdown(
    "Fuente de datos: **capa Gold** (`analytics_metrics`). El pipeline ETL "
    "(`python -m etl`) agrega Bronze→Silver→Gold para alimentar este dashboard."
)


@st.fragment(run_every=interval)
def render_dashboard():
    gold = _fetch(GOLD_SQL)
    if gold.empty:
        st.info("Todavía no hay métricas en la capa Gold. Ejecuta el pipeline ETL primero.")
        return

    total_tx = int(gold["total_transactions"].sum())
    weighted_avg_response = pd.to_numeric(gold["avg_response_time_ms"])
    response_ms = (
        (gold["total_transactions"] * weighted_avg_response).sum() / total_tx
        if total_tx and weighted_avg_response.notna().any()
        else None
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Transacciones", f"{total_tx:,}")
    c2.metric("Tokens usados", f"{int(gold['total_tokens_used'].sum()):,}")
    c3.metric("Usuarios únicos (suma de grupos)", f"{int(gold['unique_users'].sum()):,}")
    c4.metric(
        "Tiempo de respuesta promedio (ponderado)",
        f"{response_ms:,.0f} ms" if response_ms else "—",
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
        response_trend = (
            gold.groupby("metric_date")["avg_response_time_ms"].mean().sort_index()
        )
        st.line_chart(response_trend)
    with col_d:
        st.subheader("Temperatura promedio por ciudad")
        temp_by_city = gold.groupby("city")["avg_temperature"].mean().sort_values(ascending=False)
        st.bar_chart(temp_by_city)

    col_e, col_f = st.columns(2)
    with col_e:
        st.subheader("Volumen por tipo de consulta predominante")
        by_query_type = (
            gold.groupby("most_common_query_type")["total_transactions"]
            .sum()
            .sort_values(ascending=False)
        )
        st.bar_chart(by_query_type)
    with col_f:
        st.subheader("Hora pico por grupo (fecha, ciudad)")
        peak_hours = gold["peak_hour"].value_counts().sort_index()
        st.bar_chart(peak_hours)

    st.subheader("Métricas Gold por fecha y ciudad")
    st.dataframe(
        gold.sort_values(["metric_date", "city"], ascending=[False, True]),
        width="stretch",
    )

    last_agg = gold["aggregated_at"].max()
    st.caption(f"Última agregación Gold registrada: {last_agg}")


render_dashboard()