"""
Business logic for the SAR pipeline nodes.

Pure functions with no LLM calls — keeps the graph nodes thin and
makes the logic independently testable.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd
from jinja2 import Environment, FileSystemLoader

log = logging.getLogger(__name__)

_TEMPLATE_DIR = Path(__file__).parent / "templates"


# ---------------------------------------------------------------------------
# Aggregation (used by the aggregator node)
# ---------------------------------------------------------------------------

def aggregate_metrics(transactions: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute summary metrics over a list of transaction dicts using Pandas."""
    df = pd.DataFrame(transactions)

    total = len(df)
    flagged_count = int(df["is_flagged"].sum())
    flagged_df = df[df["is_flagged"] == True]  # noqa: E712

    risk_dist = df["risk_level"].dropna().value_counts().to_dict()
    txn_types = df["transaction_type"].value_counts().to_dict()
    kyc_dist = df["kyc_status"].fillna("Missing").value_counts().to_dict()

    top_reasons: list[dict[str, Any]] = []
    if len(flagged_df):
        top_reasons = [
            {"reason": r, "count": int(c)}
            for r, c in flagged_df["flag_reason"].value_counts().head(5).items()
        ]

    metrics = {
        "total_transactions": total,
        "flagged_count": flagged_count,
        "flagged_percentage": round(flagged_count / total * 100, 1) if total else 0.0,
        "pep_count": int(df["is_pep"].sum()),
        "missing_risk_count": int(df["risk_score"].isna().sum()),
        "total_volume": round(float(df["amount"].sum()), 2),
        "avg_transaction": round(float(df["amount"].mean()), 2),
        "max_transaction": round(float(df["amount"].max()), 2),
        "min_transaction": round(float(df["amount"].min()), 2),
        "flagged_volume": round(float(flagged_df["amount"].sum()), 2) if len(flagged_df) else 0.0,
        "risk_distribution": risk_dist,
        "txn_type_breakdown": txn_types,
        "kyc_breakdown": kyc_dist,
        "top_flag_reasons": top_reasons,
    }

    log.info("Aggregated %d transactions, %d flagged, volume %.2f",
             total, flagged_count, metrics["total_volume"])
    return metrics


# ---------------------------------------------------------------------------
# Missing data imputation (used by the missing-data handler node)
# ---------------------------------------------------------------------------

_RISK_THRESHOLDS = [(80, "Critical"), (60, "High"), (35, "Medium")]


def handle_missing_data(transactions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    Fill missing fields with conservative regulatory defaults.

    Defaults are intentionally cautious (e.g., unknown risk → Medium,
    unknown KYC → Pending) so that gaps surface during review rather
    than being silently dismissed.
    """
    cleaned = []
    warnings: list[str] = []

    for txn in transactions:
        rec = txn.copy()
        tid = rec.get("transaction_id", "UNKNOWN")

        if rec.get("risk_score") is None:
            rec["risk_score"] = 50.0
            rec["risk_level"] = "Medium"
            warnings.append(f"  {tid}: risk_score -> 50.0 (Medium)")
        elif rec.get("risk_level") is None:
            score = rec["risk_score"]
            level = "Low"
            for threshold, label in _RISK_THRESHOLDS:
                if score >= threshold:
                    level = label
                    break
            rec["risk_level"] = level
            warnings.append(f"  {tid}: risk_level -> '{level}'")

        if rec.get("kyc_status") is None:
            rec["kyc_status"] = "Pending"
            warnings.append(f"  {tid}: kyc_status -> 'Pending'")

        if rec.get("counterparty_name") is None:
            rec["counterparty_name"] = "UNKNOWN"
            warnings.append(f"  {tid}: counterparty_name -> 'UNKNOWN'")

        cleaned.append(rec)

    if warnings:
        log.warning("Imputed %d missing field(s):\n%s", len(warnings), "\n".join(warnings))

    return cleaned


# ---------------------------------------------------------------------------
# PDF rendering (used by the report generator node)
# ---------------------------------------------------------------------------

def _render_html(
    narrative: str,
    metrics: dict[str, Any],
    transactions: list[dict[str, Any]],
    report_id: str,
) -> str:
    """Render the Jinja2 SAR template to an HTML string."""
    env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=True)
    tpl = env.get_template("report_template.html")

    flagged = [t for t in transactions if t.get("is_flagged")]
    return tpl.render(
        report_id=report_id,
        generated_at=datetime.now().strftime("%d %B %Y, %H:%M IST"),
        narrative=narrative,
        metrics=metrics,
        flagged_transactions=flagged,
        total_transactions=len(transactions),
    )


def _pdf_via_python(html: str, dest: Path) -> None:
    from weasyprint import HTML  # type: ignore[import-untyped]
    HTML(string=html).write_pdf(str(dest))


def _find_system_weasyprint() -> str | None:
    """Locate the system weasyprint binary, skipping the venv wrapper."""
    for path in ["/usr/bin/weasyprint", "/usr/local/bin/weasyprint"]:
        if Path(path).is_file():
            return path

    # Search PATH excluding venv entries
    venv = os.environ.get("VIRTUAL_ENV", "")
    for entry in os.environ.get("PATH", "").split(os.pathsep):
        if venv and entry.startswith(venv):
            continue
        candidate = Path(entry) / "weasyprint"
        if candidate.is_file():
            return str(candidate)

    return None


def _pdf_via_cli(html: str, dest: Path) -> None:
    """Fallback: invoke the system weasyprint binary directly."""
    binary = _find_system_weasyprint()
    if not binary:
        raise RuntimeError(
            "WeasyPrint is not available as a Python import or system CLI. "
            "Install it with: sudo pacman -S weasyprint (Arch) or "
            "sudo apt install weasyprint (Debian/Ubuntu)."
        )

    with tempfile.NamedTemporaryFile(mode="w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(html)
        tmp = f.name

    try:
        result = subprocess.run(
            [binary, tmp, str(dest)],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(f"WeasyPrint CLI failed: {result.stderr}")
    finally:
        Path(tmp).unlink(missing_ok=True)


def generate_pdf(
    narrative: str,
    metrics: dict[str, Any],
    transactions: list[dict[str, Any]],
    report_id: str,
    output_path: str | Path = "output/sar_report.pdf",
) -> Path:
    """
    Render a SAR as a styled PDF (Jinja2 → HTML → WeasyPrint → PDF).

    Falls back to the system weasyprint CLI when the Python API can't
    load native libs (common in venvs on Arch due to cffi/pango mismatch).
    """
    dest = Path(output_path)
    dest.parent.mkdir(parents=True, exist_ok=True)

    html = _render_html(narrative, metrics, transactions, report_id)

    try:
        _pdf_via_python(html, dest)
        log.info("PDF generated (python API) -> %s", dest.resolve())
        return dest.resolve()
    except (OSError, ImportError) as exc:
        log.warning("WeasyPrint Python API unavailable (%s), trying CLI...", exc)

    _pdf_via_cli(html, dest)
    log.info("PDF generated (CLI fallback) -> %s", dest.resolve())
    return dest.resolve()
