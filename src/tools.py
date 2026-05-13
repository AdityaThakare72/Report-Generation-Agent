"""
src/tools.py
────────────
Standalone tool functions used by the LangGraph agent nodes.

Each function is a pure, deterministic utility — no LLM calls happen here.
This separation keeps the agent graph nodes thin (orchestration only)
and makes the business logic independently testable.
"""

from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader

logger = logging.getLogger(__name__)

_TEMPLATE_DIR: Path = Path(__file__).parent / "templates"


# ══════════════════════════════════════════════════════════════════════
#  1. AGGREGATION (Node 2)
# ══════════════════════════════════════════════════════════════════════

def aggregate_metrics(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute summary metrics from transaction dicts using Pandas.
    No LLM calls — all computation is deterministic.
    """
    df: pd.DataFrame = pd.DataFrame(transactions)

    total_transactions: int = len(df)
    flagged_count: int = int(df["is_flagged"].sum())
    pep_count: int = int(df["is_pep"].sum())
    missing_risk_count: int = int(df["risk_score"].isna().sum())

    total_volume: float = round(float(df["amount"].sum()), 2)
    avg_transaction: float = round(float(df["amount"].mean()), 2)
    max_transaction: float = round(float(df["amount"].max()), 2)
    min_transaction: float = round(float(df["amount"].min()), 2)

    flagged_df: pd.DataFrame = df[df["is_flagged"] == True]  # noqa: E712
    flagged_volume: float = round(float(flagged_df["amount"].sum()), 2) if len(flagged_df) > 0 else 0.0

    risk_distribution: dict[str, int] = df["risk_level"].dropna().value_counts().to_dict()
    txn_type_breakdown: dict[str, int] = df["transaction_type"].value_counts().to_dict()
    kyc_breakdown: dict[str, int] = df["kyc_status"].fillna("Missing").value_counts().to_dict()

    top_flag_reasons: list[dict[str, Any]] = []
    if len(flagged_df) > 0:
        reason_counts = flagged_df["flag_reason"].value_counts().head(5)
        top_flag_reasons = [
            {"reason": r, "count": int(c)} for r, c in reason_counts.items()
        ]

    metrics: dict[str, Any] = {
        "total_transactions": total_transactions,
        "flagged_count": flagged_count,
        "flagged_percentage": round(flagged_count / total_transactions * 100, 1) if total_transactions > 0 else 0.0,
        "pep_count": pep_count,
        "missing_risk_count": missing_risk_count,
        "total_volume": total_volume,
        "avg_transaction": avg_transaction,
        "max_transaction": max_transaction,
        "min_transaction": min_transaction,
        "flagged_volume": flagged_volume,
        "risk_distribution": risk_distribution,
        "txn_type_breakdown": txn_type_breakdown,
        "kyc_breakdown": kyc_breakdown,
        "top_flag_reasons": top_flag_reasons,
    }

    logger.info(
        "Aggregation complete — %d transactions, %d flagged, volume ₹%.2f",
        total_transactions, flagged_count, total_volume,
    )
    return metrics


# ══════════════════════════════════════════════════════════════════════
#  2. MISSING DATA HANDLER (Node 3)
# ══════════════════════════════════════════════════════════════════════

def handle_missing_data(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Impute missing fields with sensible defaults and log warnings.

    Rules (aligned with RBI/SEBI conservative defaults):
        risk_score   → 50.0 (mid-range, triggers "Medium")
        risk_level   → "Medium"
        kyc_status   → "Pending"
        counterparty → "UNKNOWN"
    """
    cleaned: list[dict[str, Any]] = []
    imputation_log: list[str] = []

    for txn in transactions:
        txn_id: str = txn.get("transaction_id", "UNKNOWN")
        modified: dict[str, Any] = txn.copy()

        if modified.get("risk_score") is None:
            modified["risk_score"] = 50.0
            modified["risk_level"] = "Medium"
            imputation_log.append(f"  ⚠  {txn_id}: risk_score → 50.0 (Medium)")
        elif modified.get("risk_level") is None:
            score: float = modified["risk_score"]
            if score >= 80:
                modified["risk_level"] = "Critical"
            elif score >= 60:
                modified["risk_level"] = "High"
            elif score >= 35:
                modified["risk_level"] = "Medium"
            else:
                modified["risk_level"] = "Low"
            imputation_log.append(f"  ⚠  {txn_id}: risk_level → '{modified['risk_level']}'")

        if modified.get("kyc_status") is None:
            modified["kyc_status"] = "Pending"
            imputation_log.append(f"  ⚠  {txn_id}: kyc_status → 'Pending'")

        if modified.get("counterparty_name") is None:
            modified["counterparty_name"] = "UNKNOWN"
            imputation_log.append(f"  ⚠  {txn_id}: counterparty_name → 'UNKNOWN'")

        cleaned.append(modified)

    if imputation_log:
        logger.warning("Missing data imputed in %d field(s):\n%s", len(imputation_log), "\n".join(imputation_log))
    else:
        logger.info("No missing data detected — all fields complete.")

    return cleaned


# ══════════════════════════════════════════════════════════════════════
#  3. PDF REPORT GENERATOR (Node 5)
# ══════════════════════════════════════════════════════════════════════

def _render_html(
    narrative: str,
    metrics: dict[str, Any],
    transactions: list[dict[str, Any]],
    report_id: str,
) -> str:
    """Render the Jinja2 SAR template to an HTML string."""
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    template = env.get_template("report_template.html")

    flagged_transactions: list[dict[str, Any]] = [
        txn for txn in transactions if txn.get("is_flagged")
    ]

    return template.render(
        report_id=report_id,
        generated_at=datetime.now().strftime("%d %B %Y, %H:%M IST"),
        narrative=narrative,
        metrics=metrics,
        flagged_transactions=flagged_transactions,
        total_transactions=len(transactions),
    )


def _pdf_via_python(html_content: str, output_path: Path) -> None:
    """Attempt PDF generation via the WeasyPrint Python API."""
    from weasyprint import HTML  # type: ignore[import-untyped]
    HTML(string=html_content).write_pdf(str(output_path))


def _pdf_via_cli(html_content: str, output_path: Path) -> None:
    """Fallback: use the system `weasyprint` CLI binary (outside venv)."""
    import os

    # Prefer the system binary — the venv wrapper has the same cffi issue
    weasyprint_bin: str | None = None
    for candidate in ["/usr/bin/weasyprint", "/usr/local/bin/weasyprint"]:
        if Path(candidate).is_file():
            weasyprint_bin = candidate
            break

    # Last resort: search PATH but skip venv entries
    if not weasyprint_bin:
        venv_prefix: str = os.environ.get("VIRTUAL_ENV", "")
        for p in os.environ.get("PATH", "").split(os.pathsep):
            if venv_prefix and p.startswith(venv_prefix):
                continue
            candidate_path = Path(p) / "weasyprint"
            if candidate_path.is_file():
                weasyprint_bin = str(candidate_path)
                break

    if not weasyprint_bin:
        raise RuntimeError(
            "WeasyPrint is not available as a Python import or system CLI. "
            "Install it with: sudo pacman -S weasyprint (Arch) or "
            "sudo apt install weasyprint (Debian/Ubuntu)."
        )

    # Write HTML to a temporary file for the CLI
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".html", delete=False, encoding="utf-8"
    ) as tmp:
        tmp.write(html_content)
        tmp_path: str = tmp.name

    try:
        result = subprocess.run(
            [weasyprint_bin, tmp_path, str(output_path)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"WeasyPrint CLI failed: {result.stderr}")
    finally:
        Path(tmp_path).unlink(missing_ok=True)


def generate_pdf(
    narrative: str,
    metrics: dict[str, Any],
    transactions: list[dict[str, Any]],
    report_id: str,
    output_path: str | Path = "output/sar_report.pdf",
) -> Path:
    """
    Render a Suspicious Activity Report as PDF.

    Pipeline: Jinja2 (HTML) → WeasyPrint (PDF).

    Uses the Python WeasyPrint API if available, otherwise falls back
    to the system `weasyprint` CLI (common on Arch Linux where
    venv cffi can have symbol mismatches with system pango/glib).
    """
    output: Path = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    html_content: str = _render_html(narrative, metrics, transactions, report_id)

    # Strategy 1: Python API (fastest, works on most systems)
    try:
        _pdf_via_python(html_content, output)
        logger.info("PDF generated (Python API) → %s", output.resolve())
        return output.resolve()
    except (OSError, ImportError) as e:
        logger.warning("WeasyPrint Python API unavailable (%s), trying CLI fallback...", e)

    # Strategy 2: System CLI fallback
    _pdf_via_cli(html_content, output)
    logger.info("PDF generated (CLI fallback) → %s", output.resolve())
    return output.resolve()
