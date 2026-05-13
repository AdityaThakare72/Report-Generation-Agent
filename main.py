"""
Entry point for the SAR Report Drafting Agent.

Usage:
    python main.py                              # default data file
    python main.py data/sample_transactions.json
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()  # must run before langchain imports

from src.agent import AgentState, sar_pipeline  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("main")

DEFAULT_INPUT = "data/sample_transactions.json"


def main(input_path: str = DEFAULT_INPUT) -> None:
    data_file = Path(input_path)
    if not data_file.exists():
        log.error("Input file not found: %s", data_file)
        log.info("Run 'python -m src.data_generator' to create sample data.")
        sys.exit(1)

    log.info("Loading %s", data_file)
    with open(data_file, encoding="utf-8") as f:
        raw_data = json.load(f)

    log.info("Loaded %d transactions (report %s)",
             len(raw_data.get("transactions", [])),
             raw_data.get("report_id", "UNKNOWN"))

    initial_state: AgentState = {
        "raw_data": raw_data,
        "cleaned_data": [],
        "aggregated_metrics": {},
        "narrative": "",
        "final_report_path": "",
    }

    print("\n--- SAR Report Agent ---\n")

    result = sar_pipeline.invoke(initial_state)

    report_path = result.get("final_report_path", "")
    print(f"\nDone. Report written to: {report_path}\n")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else DEFAULT_INPUT)
