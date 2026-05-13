"""
main.py
───────
Entry point for the AI Compliance Monitoring — SAR Report Drafting Agent.

Usage:
    python main.py                              # Uses default data file
    python main.py data/sample_transactions.json # Custom input path
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

# ── Load environment variables BEFORE any LangChain imports ──────────
load_dotenv()

from src.agent import AgentState, sar_pipeline  # noqa: E402

# ── Logging configuration ────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s │ %(levelname)-7s │ %(name)s │ %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("main")

# ── Constants ────────────────────────────────────────────────────────
DEFAULT_INPUT: str = "data/sample_transactions.json"


def main(input_path: str = DEFAULT_INPUT) -> None:
    """
    Load transaction data, invoke the LangGraph SAR pipeline,
    and print the path to the generated PDF.
    """
    # ── 1. Load input data ───────────────────────────────────────
    data_file = Path(input_path)
    if not data_file.exists():
        logger.error("Input file not found: %s", data_file)
        logger.info("Run 'python -m src.data_generator' first to create sample data.")
        sys.exit(1)

    logger.info("Loading transaction data from %s", data_file)
    with open(data_file, "r", encoding="utf-8") as f:
        raw_data: dict = json.load(f)

    logger.info(
        "Loaded %d transactions (Report ID: %s)",
        len(raw_data.get("transactions", [])),
        raw_data.get("report_id", "UNKNOWN"),
    )

    # ── 2. Prepare initial state ─────────────────────────────────
    initial_state: AgentState = {
        "raw_data": raw_data,
        "cleaned_data": [],
        "aggregated_metrics": {},
        "narrative": "",
        "final_report_path": "",
    }

    # ── 3. Run the LangGraph pipeline ────────────────────────────
    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   AI Compliance Monitoring — SAR Report Agent           ║")
    print("╚══════════════════════════════════════════════════════════╝")
    print()

    final_state = sar_pipeline.invoke(initial_state)

    # ── 4. Output results ────────────────────────────────────────
    report_path: str = final_state.get("final_report_path", "")

    print()
    print("╔══════════════════════════════════════════════════════════╗")
    print("║   ✅  SAR Report Generated Successfully                 ║")
    print("╠══════════════════════════════════════════════════════════╣")
    print(f"║   📄 PDF: {report_path:<46} ║" if len(report_path) <= 46
          else f"║   📄 PDF: {report_path}")
    print("╚══════════════════════════════════════════════════════════╝")
    print()


if __name__ == "__main__":
    input_file: str = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT
    main(input_file)
