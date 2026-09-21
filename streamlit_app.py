"""Streamlit frontend for the Climate Risk Q&A agent.

Makes the anti-hallucination stack visible to the end user, not just the
audit log: KG nodes traversed, dataset verification ticks, faithfulness
score, tier, and cost are all surfaced alongside the answer.
"""

from __future__ import annotations

import requests
import streamlit as st

API_URL = "http://localhost:8000/query"

st.set_page_config(page_title="Climate Risk Q&A", page_icon="🌍", layout="wide")
st.title("🌍 Climate Risk Q&A — Governed Multi-Agent System")
st.caption(
    "KG + SQL + pgvector grounded answers. Structurally cannot hallucinate "
    "datasets. Fully auditable."
)

query = st.text_input(
    "Ask a climate risk question",
    placeholder="e.g. What is the projected flood risk for Kerala under SSP5-8.5?",
)

if st.button("Submit") and query:
    with st.spinner("Running governed pipeline..."):
        try:
            response = requests.post(API_URL, json={"query": query}, timeout=60)
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            st.error(f"Request failed: {exc}")
            data = None

    if data:
        if data.get("status") == "paused":
            st.warning(data["message"])
        else:
            st.subheader("Answer")
            st.write(data.get("final_answer"))

            analysis = data.get("analysis_results") or {}
            chart_b64 = analysis.get("chart_base64")
            if chart_b64:
                import base64

                st.image(base64.b64decode(chart_b64), caption="Generated chart")

            col1, col2, col3 = st.columns(3)
            col1.metric("Tier assigned", data.get("tier_assigned") or "n/a")
            col2.metric("Faithfulness", f"{(data.get('groundedness_score') or 0):.2f}")
            col3.metric("Cost (USD)", f"${data.get('litellm_cost_usd', 0):.4f}")

            if data.get("human_approval_required"):
                st.warning("This is a Tier 2 recommendation — human confirmation required before proceeding.")

            st.subheader("Knowledge graph path traversed")
            kg_results = data.get("kg_results") or {}
            st.json(kg_results.get("nodes_traversed", []))

            st.subheader("Datasets cited (KG-verified)")
            dataset = kg_results.get("dataset")
            if dataset:
                st.markdown(f"✅ **{dataset}** — verified against knowledge graph")
            else:
                st.markdown("_No dataset citation for this query._")

            st.subheader("Retrieved evidence")
            for chunk in data.get("rag_results") or []:
                with st.expander(f"{chunk['source_doc']} (p.{chunk['page_number']})"):
                    st.write(chunk["content"])

            st.subheader("Trace ID")
            st.code(data.get("trace_id"))
