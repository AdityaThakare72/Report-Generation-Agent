"""
LangGraph StateGraph implementing the 5-node SAR compliance pipeline.

Flow: map_fields -> handle_missing -> aggregate -> generate_narrative -> generate_report
"""

from __future__ import annotations

import json
import logging
from typing import Any, TypedDict

from langchain_core.messages import HumanMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph

from src.models import REGULATORY_FIELD_MAP, TransactionBatch
from src.tools import aggregate_metrics, generate_pdf, handle_missing_data

log = logging.getLogger(__name__)


class AgentState(TypedDict):
    raw_data: dict[str, Any]
    cleaned_data: list[dict[str, Any]]
    aggregated_metrics: dict[str, Any]
    narrative: str
    final_report_path: str


# ---------------------------------------------------------------------------
# Node implementations
# ---------------------------------------------------------------------------

def map_fields_node(state: AgentState) -> dict[str, Any]:
    """Validate raw JSON via Pydantic and map to regulatory field names."""
    log.info("Node 1: Field Mapper")

    batch = TransactionBatch(**state["raw_data"])
    log.info("Validated %d transactions for report %s",
             len(batch.transactions), batch.report_id)

    transactions = [txn.model_dump(mode="json") for txn in batch.transactions]

    log.info("Regulatory field mapping loaded (%d fields)", len(REGULATORY_FIELD_MAP))
    return {"cleaned_data": transactions}


def handle_missing_node(state: AgentState) -> dict[str, Any]:
    """Impute missing fields with conservative defaults."""
    log.info("Node 2: Missing Data Handler")
    return {"cleaned_data": handle_missing_data(state["cleaned_data"])}


def aggregate_node(state: AgentState) -> dict[str, Any]:
    """Compute summary metrics with Pandas."""
    log.info("Node 3: Aggregator")
    return {"aggregated_metrics": aggregate_metrics(state["cleaned_data"])}


_NARRATIVE_PROMPT = """You are a senior financial compliance officer at a regulated Indian financial institution.
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
    """Generate a compliance narrative from aggregated metrics via Gemini."""
    log.info("Node 4: Narrative Generator")

    metrics_json = json.dumps(state["aggregated_metrics"], indent=2, default=str)

    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.3,
        max_output_tokens=1024,
    )

    prompt = _NARRATIVE_PROMPT.format(metrics_json=metrics_json)
    response = llm.invoke([HumanMessage(content=prompt)])

    log.info("Narrative generated (%d chars)", len(response.content))
    return {"narrative": response.content}


def generate_report_node(state: AgentState) -> dict[str, Any]:
    """Render the final SAR PDF."""
    log.info("Node 5: Report Generator")

    report_id = state["raw_data"].get("report_id", "SAR-UNKNOWN")
    pdf_path = generate_pdf(
        narrative=state["narrative"],
        metrics=state["aggregated_metrics"],
        transactions=state["cleaned_data"],
        report_id=report_id,
        output_path=f"output/{report_id}.pdf",
    )

    log.info("Final PDF -> %s", pdf_path)
    return {"final_report_path": str(pdf_path)}


# ---------------------------------------------------------------------------
# Graph assembly
# ---------------------------------------------------------------------------

def build_graph():
    """Construct and compile the 5-node SAR pipeline."""
    g = StateGraph(AgentState)

    g.add_node("map_fields", map_fields_node)
    g.add_node("handle_missing", handle_missing_node)
    g.add_node("aggregate", aggregate_node)
    g.add_node("generate_narrative", generate_narrative_node)
    g.add_node("generate_report", generate_report_node)

    g.set_entry_point("map_fields")
    g.add_edge("map_fields", "handle_missing")
    g.add_edge("handle_missing", "aggregate")
    g.add_edge("aggregate", "generate_narrative")
    g.add_edge("generate_narrative", "generate_report")
    g.add_edge("generate_report", END)

    return g.compile()


sar_pipeline = build_graph()
