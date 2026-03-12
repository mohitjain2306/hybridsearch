# frontend/app.py

import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
import pandas as pd
import requests
from datetime import datetime

API_BASE = "http://localhost:8000/api/v1"
HEALTH_URL = "http://localhost:8000/api/v1/health"

CATEGORIES = [
    "all", "space", "medicine", "technology", "science", "history",
    "geography", "economics", "sports", "culture", "nature", "society", "general",
]

st.set_page_config(
    page_title="Knowledge Search",
    page_icon="🔍",
    layout="wide",
)

# ---------------------------------------------------------------------------
# API helpers
# ---------------------------------------------------------------------------

def api_get(path: str, params: dict = None) -> dict | None:
    try:
        r = requests.get(f"{API_BASE}{path}", params=params, timeout=10)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach API at http://localhost:8000 — is it running?")
    except requests.exceptions.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")
    return None


def api_post(path: str, payload: dict) -> dict | None:
    try:
        r = requests.post(f"{API_BASE}{path}", json=payload, timeout=30)
        r.raise_for_status()
        return r.json()
    except requests.exceptions.ConnectionError:
        st.error("Cannot reach API at http://localhost:8000 — is it running?")
    except requests.exceptions.HTTPError as e:
        st.error(f"API error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")
    return None


def fetch_health() -> dict | None:
    try:
        r = requests.get(HEALTH_URL, timeout=5)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Sidebar — navigation + health badge
# ---------------------------------------------------------------------------

with st.sidebar:
    st.title("🔍 Knowledge Search")
    st.divider()

    page = st.radio(
        "Navigate",
        ["Search", "KPIs", "Evaluation", "Debug Logs"],
        label_visibility="collapsed",
    )

    st.divider()
    st.caption("API Health")

    health = fetch_health()
    if health is None:
        st.error("🔴  API unreachable")
    else:
        status_icon = "🟢" if health.get("indexes_loaded") else "🟡"
        st.success(f"{status_icon}  API online")
        st.caption(f"Version: {health.get('version', '—')}")
        st.caption(f"Commit:  `{health.get('git_commit', '—')}`")
        if not health.get("indexes_loaded"):
            st.warning("Indexes not loaded — run build_index.py")
        st.caption(f"Queries served: {health.get('total_queries_served', 0):,}")


# ---------------------------------------------------------------------------
# Page 1 — Search
# ---------------------------------------------------------------------------

if page == "Search":
    st.header("Search")

    with st.form("search_form"):
        query = st.text_input("Query", placeholder="e.g. NASA space exploration")

        col1, col2, col3 = st.columns([3, 2, 2])
        with col1:
            alpha = st.slider(
                "Alpha  (0 = semantic · 1 = keyword)",
                min_value=0.0, max_value=1.0,
                value=0.5, step=0.05,
            )
        with col2:
            top_k = st.number_input(
                "Results (top_k)",
                min_value=1, max_value=20, value=10, step=1,
            )
        with col3:
            category = st.selectbox("Category filter", CATEGORIES)

        submitted = st.form_submit_button("🔍  Search", use_container_width=True)

    if submitted:
        if not query.strip():
            st.warning("Please enter a query.")
        else:
            payload = {
                "query": query,
                "alpha": alpha,
                "top_k": int(top_k),
                "filters": {"category": category} if category != "all" else None,
            }

            with st.spinner("Searching…"):
                data = api_post("/search", payload)

            if data:
                rc  = data.get("result_count", 0)
                lat = data.get("latency_ms",   0.0)
                rid = data.get("request_id",   "—")

                m1, m2, m3 = st.columns(3)
                m1.metric("Results",      rc)
                m2.metric("Latency",      f"{lat:.1f} ms")
                m3.metric("Request ID",   rid[:8] + "…")

                st.divider()

                results = data.get("results", [])
                if not results:
                    st.info("No results found. Try a different query or alpha value.")
                else:
                    for i, r in enumerate(results):
                        with st.expander(
                            f"**{r['title']}**  —  score {r['score']:.4f}",
                            expanded=(i == 0),
                        ):
                            col_left, col_right = st.columns([2, 3])

                            with col_left:
                                st.markdown(f"**Snippet:** {r.get('snippet', '')}")
                                st.caption(f"doc_id: `{r['doc_id']}`")
                                st.caption(f"category: {r.get('category', '—')}")
                                st.caption(f"chunk: {r.get('chunk_index', 0)}")

                            with col_right:
                                fig = go.Figure(go.Bar(
                                    x=[
                                        r.get("bm25_score",   0.0),
                                        r.get("vector_score", 0.0),
                                        r.get("score",        0.0),
                                    ],
                                    y=["BM25", "Vector", "Hybrid"],
                                    orientation="h",
                                    marker_color=["#4C78A8", "#F58518", "#54A24B"],
                                    text=[
                                        f"{r.get('bm25_score',   0.0):.4f}",
                                        f"{r.get('vector_score', 0.0):.4f}",
                                        f"{r.get('score',        0.0):.4f}",
                                    ],
                                    textposition="outside",
                                ))
                                fig.update_layout(
                                    height=160,
                                    margin=dict(l=10, r=30, t=10, b=10),
                                    xaxis=dict(range=[0, 1.05]),
                                    showlegend=False,
                                )
                                st.plotly_chart(
                                    fig,
                                    use_container_width=True,
                                    key=f"score_chart_{rid}_{i}",
                                )


# ---------------------------------------------------------------------------
# Page 2 — KPIs
# ---------------------------------------------------------------------------

elif page == "KPIs":
    st.header("KPIs")

    data = api_get("/logs", params={"limit": 1000})
    if not data:
        st.stop()

    logs = data.get("logs", [])
    if not logs:
        st.info("No query logs yet — run some searches first.")
        st.stop()

    df = pd.DataFrame(logs)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["hour"]      = df["timestamp"].dt.floor("h")

    # ── Metric cards ──────────────────────────────────────────────────────
    total_q    = len(df)
    zero_res   = int((df["result_count"] == 0).sum())
    ok_lat     = df.loc[df["error"].isna(), "latency_ms"]
    p50        = float(ok_lat.quantile(0.50)) if len(ok_lat) else 0.0
    p95        = float(ok_lat.quantile(0.95)) if len(ok_lat) else 0.0

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Total Queries",       f"{total_q:,}")
    c2.metric("p50 Latency",         f"{p50:.1f} ms")
    c3.metric("p95 Latency",         f"{p95:.1f} ms")
    c4.metric("Zero-result Queries", f"{zero_res:,}")

    st.divider()

    col_left, col_right = st.columns(2)

    # ── Request volume by hour ────────────────────────────────────────────
    # ── Request volume by hour ────────────────────────────────────────────
    with col_left:
        st.subheader("Request volume by hour")
        vol = df.groupby("hour").size().reset_index(name="Requests")
        fig_vol = px.bar(
            vol, x="hour", y="Requests",
            labels={"hour": "Hour"},
            color="Requests",
            color_continuous_scale="Blues",
        )
        fig_vol.update_layout(
            margin=dict(t=20, b=20),
            coloraxis_showscale=False,
            xaxis_tickformat="%H:%M",
        )
        st.plotly_chart(fig_vol, use_container_width=True, key="kpi_volume")

    # ── Latency histogram ─────────────────────────────────────────────────
    with col_right:
        st.subheader("Latency distribution")
        # cap at 99th percentile to hide outliers
        p99 = float(ok_lat.quantile(0.99)) if len(ok_lat) else 5000
        ok_lat_capped = ok_lat[ok_lat <= p99]
        fig_lat = px.histogram(
            ok_lat_capped, nbins=20,
            labels={"value": "Latency (ms)", "count": "Queries"},
            color_discrete_sequence=["#4C78A8"],
        )
        fig_lat.update_layout(
            showlegend=False,
            margin=dict(t=20, b=20),
            xaxis_title="Latency (ms)",
            yaxis_title="Queries",
        )
        st.plotly_chart(fig_lat, use_container_width=True, key="kpi_latency")

    # ── Top 10 queries ────────────────────────────────────────────────────
    st.subheader("Top 10 queries")
    top_q = (
        df.groupby("query")
          .agg(count=("query", "size"), avg_latency=("latency_ms", "mean"))
          .sort_values("count", ascending=False)
          .head(10)
          .reset_index()
    )
    top_q["avg_latency"] = top_q["avg_latency"].round(1)

    fig_top = px.bar(
        top_q, x="count", y="query",
        orientation="h",
        labels={"count": "Searches", "query": "Query"},
        color="avg_latency",
        color_continuous_scale="Teal",
        text="count",
    )
    fig_top.update_layout(
        margin=dict(t=20, b=20),
        yaxis=dict(autorange="reversed"),
        coloraxis_colorbar=dict(title="Avg ms"),
        height=350,
    )
    fig_top.update_traces(textposition="outside")
    st.plotly_chart(fig_top, use_container_width=True, key="kpi_top_queries")


# ---------------------------------------------------------------------------
# Page 3 — Evaluation
# ---------------------------------------------------------------------------

elif page == "Evaluation":
    st.header("Evaluation")

    import os
    csv_path = os.path.join(os.path.dirname(__file__), "..", "data", "metrics", "experiments.csv")
    try:
        df_eval = pd.read_csv(csv_path)
    except FileNotFoundError:
        st.warning(
            f"`{csv_path}` not found. "
            "Run `python -m app.eval` and save results to that path to populate this page."
        )
        st.stop()
    except Exception as e:
        st.error(f"Could not read {csv_path}: {e}")
        st.stop()

    st.subheader("All experiments")
    st.dataframe(df_eval, use_container_width=True)

    st.divider()

    # Require at minimum: alpha, ndcg_at_k, recall_at_k, mrr
    required_cols = {"alpha", "ndcg_at_10", "recall_at_10", "mrr"}
    if not required_cols.issubset(df_eval.columns):
        missing = required_cols - set(df_eval.columns)
        st.error(f"CSV is missing required columns: {missing}")
        st.stop()

    col_left, col_right = st.columns(2)

    # ── nDCG line chart ───────────────────────────────────────────────────
    with col_left:
        st.subheader("nDCG@10 over experiment runs")
        run_col = "run" if "run" in df_eval.columns else df_eval.index.name or "index"
        fig_ndcg = px.line(
            df_eval.reset_index(), x="index", y="ndcg_at_10",
            markers=True,
            labels={"index": "Run", "ndcg_at_10": "nDCG@10"},
        )
        fig_ndcg.update_layout(margin=dict(t=20, b=20))
        st.plotly_chart(fig_ndcg, use_container_width=True, key="eval_ndcg")

    # ── Scatter: recall by alpha ──────────────────────────────────────────
    with col_right:
        st.subheader("Recall@10 by alpha")
        fig_rec = px.scatter(
            df_eval, x="alpha", y="recall_at_10",
            size_max=10,
            labels={"alpha": "Alpha", "recall_at_10": "Recall@10"},
        )
        fig_rec.update_layout(margin=dict(t=20, b=20))
        st.plotly_chart(fig_rec, use_container_width=True, key="eval_recall")

    st.subheader("MRR by alpha")
    fig_mrr = px.scatter(
        df_eval, x="alpha", y="mrr",
        labels={"alpha": "Alpha", "mrr": "MRR"},
        color="mrr",
        color_continuous_scale="Viridis",
    )
    fig_mrr.update_layout(margin=dict(t=20, b=20), height=350)
    st.plotly_chart(fig_mrr, use_container_width=True, key="eval_mrr")


# ---------------------------------------------------------------------------
# Page 4 — Debug Logs
# ---------------------------------------------------------------------------

elif page == "Debug Logs":
    st.header("Debug Logs")

    col_ctrl1, col_ctrl2 = st.columns([2, 1])
    with col_ctrl1:
        limit = st.slider("Max logs to fetch", 50, 1000, 200, step=50)
    with col_ctrl2:
        severity_filter = st.selectbox("Severity", ["ALL", "INFO", "ERROR"])

    data = api_get("/logs", params={"limit": limit})
    if not data:
        st.stop()

    logs = data.get("logs", [])
    if not logs:
        st.info("No logs found.")
        st.stop()

    df = pd.DataFrame(logs)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["severity"]  = df["error"].apply(lambda e: "ERROR" if pd.notna(e) and e else "INFO")

    if severity_filter != "ALL":
        df = df[df["severity"] == severity_filter]

    if df.empty:
        st.info(f"No {severity_filter} logs found.")
        st.stop()

    error_count = int((df["severity"] == "ERROR").sum())
    info_count  = int((df["severity"] == "INFO").sum())

    sc1, sc2, sc3 = st.columns(3)
    sc1.metric("Shown",  len(df))
    sc2.metric("INFO",   info_count)
    sc3.metric("ERROR",  error_count, delta=None if error_count == 0 else f"{error_count} errors")

    display_cols = ["timestamp", "severity", "query", "alpha", "latency_ms", "result_count", "error"]
    display_cols = [c for c in display_cols if c in df.columns]

    st.dataframe(
        df[display_cols].sort_values("timestamp", ascending=False),
        use_container_width=True,
        column_config={
            "timestamp":    st.column_config.DatetimeColumn("Time",    format="YYYY-MM-DD HH:mm:ss"),
            "severity":     st.column_config.TextColumn("Severity"),
            "query":        st.column_config.TextColumn("Query",       width="medium"),
            "alpha":        st.column_config.NumberColumn("Alpha",     format="%.2f"),
            "latency_ms":   st.column_config.NumberColumn("Latency ms",format="%.1f"),
            "result_count": st.column_config.NumberColumn("Results"),
            "error":        st.column_config.TextColumn("Error",       width="large"),
        },
    )