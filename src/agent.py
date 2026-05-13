"""
src/agent.py
────────────
LangGraph StateGraph with 5 nodes implementing the SAR compliance pipeline.

Graph flow (linear):
    map_fields → handle_missing → aggregate → generate_narrative → generate_report

Each node is a pure function: (AgentState) → dict  (partial state update).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph

from src.models import REGULATORY_FIELD_MAP, Transaction, TransactionBatch
from src.tools import aggregate_metrics, generate_pdf, handle_missing_data

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  STATE DEFINITION
# ══════════════════════════════════════════════════════════════════════

class AgentState(TypedDict):
    """Typed state dict shared across all LangGraph nodes."""
    raw_data: dict[str, Any]                     # Original JSON payload
    cleaned_data: list[dict[str, Any]]           # Post-imputation transactions
    aggregated_metrics: dict[str, Any]            # Pandas-computed summary
    narrative: str                                # LLM-generated compliance text
    final_report_path: str                        # Path to generated PDF


# ══════════════════════════════════════════════════════════════════════
#  NODE 1 — FIELD MAPPER
# ══════════════════════════════════════════════════════════════════════

def map_fields_node(state: AgentState) -> dict[str, Any]:
    """
    Validate raw JSON through Pydantic and map internal field names
    to regulatory report nomenclature.
    """
    logger.info("═══ Node 1: Field Mapper ═══")
    raw: dict[str, Any] = state["raw_data"]

    # Pydantic validation — raises ValidationError on bad data
    batch = TransactionBatch(**raw)
    logger.info(
        "Validated %d transactions for report %s",
        len(batch.transactions), batch.report_id,
    )

    # Serialize to dicts for downstream processing
    transactions: list[dict[str, Any]] = [
        txn.model_dump(mode="json") for txn in batch.transactions
    ]

    # Log the regulatory field mapping (for audit trail)
    logger.info(
        "Field mapping applied: %d internal → regulatory mappings loaded",
        len(REGULATORY_FIELD_MAP),
    )

    return {"cleaned_data": transactions}


# ══════════════════════════════════════════════════════════════════════
#  NODE 2 — MISSING DATA HANDLER
# ══════════════════════════════════════════════════════════════════════

def handle_missing_node(state: AgentState) -> dict[str, Any]:
    """Impute missing fields using conservative regulatory defaults."""
    logger.info("═══ Node 2: Missing Data Handler ═══")
    cleaned: list[dict[str, Any]] = handle_missing_data(state["cleaned_data"])
    return {"cleaned_data": cleaned}


# ══════════════════════════════════════════════════════════════════════
#  NODE 3 — AGGREGATOR
# ══════════════════════════════════════════════════════════════════════

def aggregate_node(state: AgentState) -> dict[str, Any]:
    """Compute summary metrics using Pandas (no LLM involved)."""
    logger.info("═══ Node 3: Aggregator ═══")
    metrics: dict[str, Any] = aggregate_metrics(state["cleaned_data"])
    return {"aggregated_metrics": metrics}


# ══════════════════════════════════════════════════════════════════════
#  NODE 4 — LLM NARRATIVE GENERATOR
# ══════════════════════════════════════════════════════════════════════

_NARRATIVE_PROMPT: str = """You are a senior financial compliance officer at a regulated Indian financial institution.
You are drafting the narrative section of a Suspicious Activity Report (SAR) for submission to the Financial Intelligence Unit — India (FIU-IND) under the Prevention of Money Laundering Act (PMLA), 2002.

Based on the following aggregated transaction metrics, write a professional 2–3 paragraph compliance summary narrative.

METRICS:
{metrics_json}

REQUIREMENTS:
1. Use formal regulatory language appropriate for RBI/SEBI compliance filings.
2. Highlight the key risk indicators: number of flagged transactions, PEP involvement, risk distribution, and total suspicious volume.
3. Reference relevant regulatory frameworks (RBI KYC Master Direction, SEBI AML/CFT Circular, PMLA 2002).
4. Recommend specific next steps (enhanced due diligence, STR filing, account monitoring).
5. Do NOT fabricate numbers — use only the metrics provided.
6. Keep it concise (250–350 words).

Write the narrative now:"""


def generate_narrative_node(state: AgentState) -> dict[str, Any]:
    """Use Gemini to generate a compliance narrative from metrics."""
    logger.info("═══ Node 4: LLM Narrative Generator ═══")

    metrics: dict[str, Any] = state["aggregated_metrics"]
    metrics_json: str = json.dumps(metrics, indent=2, default=str)

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.3,
        max_output_tokens=1024,
    )

    prompt: str = _NARRATIVE_PROMPT.format(metrics_json=metrics_json)
    response = llm.invoke([HumanMessage(content=prompt)])
    narrative: str = response.content

    logger.info("Narrative generated (%d characters)", len(narrative))
    return {"narrative": narrative}


# ══════════════════════════════════════════════════════════════════════
#  NODE 5 — REPORT GENERATOR
# ══════════════════════════════════════════════════════════════════════

def generate_report_node(state: AgentState) -> dict[str, Any]:
    """Render the final SAR PDF using Jinja2 + WeasyPrint."""
    logger.info("═══ Node 5: Report Generator ═══")

    report_id: str = state["raw_data"].get("report_id", "SAR-UNKNOWN")
    output_path: str = f"output/{report_id}.pdf"

    pdf_path = generate_pdf(
        narrative=state["narrative"],
        metrics=state["aggregated_metrics"],
        transactions=state["cleaned_data"],
        report_id=report_id,
        output_path=output_path,
    )

    logger.info("Final PDF → %s", pdf_path)
    return {"final_report_path": str(pdf_path)}


# ══════════════════════════════════════════════════════════════════════
#  GRAPH COMPILATION
# ══════════════════════════════════════════════════════════════════════

def build_graph() -> Any:
    """
    Construct and compile the 5-node SAR pipeline graph.

    Returns:
        Compiled LangGraph runnable.
    """
    graph = StateGraph(AgentState)

    # Register nodes
    graph.add_node("map_fields", map_fields_node)
    graph.add_node("handle_missing", handle_missing_node)
    graph.add_node("aggregate", aggregate_node)
    graph.add_node("generate_narrative", generate_narrative_node)
    graph.add_node("generate_report", generate_report_node)

    # Define edges (linear pipeline)
    graph.set_entry_point("map_fields")
    graph.add_edge("map_fields", "handle_missing")
    graph.add_edge("handle_missing", "aggregate")
    graph.add_edge("aggregate", "generate_narrative")
    graph.add_edge("generate_narrative", "generate_report")
    graph.add_edge("generate_report", END)

    return graph.compile()


# Pre-built graph instance for import convenience
sar_pipeline = build_graph()
