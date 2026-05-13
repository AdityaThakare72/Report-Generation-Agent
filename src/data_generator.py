"""
src/data_generator.py
─────────────────────
Fabricates 50 rows of realistic financial transaction data for
testing the AI Compliance Monitoring SAR pipeline.

Run directly:
    python -m src.data_generator

Output:
    data/sample_transactions.json

Design decisions:
    • ~30 % of transactions are intentionally flagged (high-risk)
      to produce meaningful SAR narratives.
    • ~10 % of records have missing risk_score / kyc_status to
      exercise Node 3 (Missing Data Handler).
    • Amounts follow a log-normal distribution to mimic real
      financial transaction patterns (many small, few very large).
    • Indian names, IFSC codes, and INR-denominated amounts give
      the data an RBI/SEBI regulatory flavour.
"""

from __future__ import annotations

import json
import math
import os
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.models import (
    AccountType,
    Currency,
    RiskLevel,
    Transaction,
    TransactionBatch,
    TransactionType,
)

# ──────────────────────────────────────────────────────────────────────
# Constants & Reference Data
# ──────────────────────────────────────────────────────────────────────

NUM_TRANSACTIONS: int = 50

# Realistic Indian names
CUSTOMER_NAMES: list[str] = [
    "Rajesh Kumar Sharma", "Priya Nair", "Amit Patel",
    "Sunita Devi Gupta", "Vikram Singh Chauhan", "Ananya Iyer",
    "Mohammed Farooq Sheikh", "Deepa Krishnamurthy", "Arjun Reddy",
    "Kavitha Balasubramanian", "Rohan Mehta", "Neha Agarwal",
    "Siddharth Joshi", "Pooja Saxena", "Manoj Tiwari",
    "Fatima Begum", "Ravi Shankar Mishra", "Lakshmi Venkatesh",
    "Gaurav Kapoor", "Nandini Deshmukh", "Suresh Babu",
    "Meera Rajput", "Anil Kumar Verma", "Swathi Narayan",
    "Prakash Chandra Das",
]

COUNTERPARTY_NAMES: list[str] = [
    "Offshore Holdings Ltd", "Global Trade FZE",
    "Pinnacle Investments LLC", "Star Exports Pvt Ltd",
    "Diamond Bullion Traders", "Zenith Capital Partners",
    "Crescent Finance Co", "Lotus Shipping Corp",
    "Eagle Remittance Services", "Sapphire Commodities",
    "Phoenix Industries Ltd", "Meridian Consulting Group",
    "Eastern Promise Trading", "Continental Forex Bureau",
    "Alpine Trust Holdings",
]

# Sample IFSC-style codes
BRANCH_CODES: list[str] = [
    "HDFC0001234", "SBIN0005678", "ICIC0009012",
    "UTIB0003456", "KKBK0007890", "PUNB0002345",
    "BARB0006789", "CNRB0001111", "BKID0002222",
    "IOBA0003333",
]

COUNTERPARTY_BANKS: list[str] = [
    "HSBC0005678", "CITI0001234", "SCBL0009876",
    "DBSS0004321", "BARB0008765", "SBIN0001111",
    "ICIC0002222",
]

FLAG_REASONS: list[str] = [
    "Large outward remittance to high-risk jurisdiction",
    "Structuring — multiple deposits just below ₹10L threshold",
    "Rapid movement of funds (round-tripping suspected)",
    "Transaction inconsistent with declared income profile",
    "Counterparty on internal watchlist",
    "Unusual cash deposit pattern — potential smurfing",
    "PEP-related transaction exceeding threshold",
    "Dormant account reactivated with large transfer",
    "Multiple beneficiaries from same IP address",
    "Cross-border transfer to sanctioned country",
]

KYC_STATUSES: list[str | None] = [
    "Verified", "Verified", "Verified", "Verified",  # 60 % verified
    "Pending", "Pending",                             # 20 % pending
    "Expired",                                        # 10 % expired
    None,                                             # 10 % missing
]

REMARKS_POOL: list[str | None] = [
    "Flagged for manual review — unusual pattern",
    "Escalated to senior compliance officer",
    "Customer provided supporting documentation",
    "Pending clarification from branch",
    "Cleared after secondary review",
    None, None, None,  # ~37.5 % chance of no remark
]


# ──────────────────────────────────────────────────────────────────────
# Helper functions
# ──────────────────────────────────────────────────────────────────────

def _random_amount() -> float:
    """
    Generate a log-normally distributed transaction amount in INR.
    Most transactions cluster around ₹50K–₹5L, with occasional
    outliers up to ₹2Cr+.
    """
    raw: float = random.lognormvariate(mu=12.0, sigma=1.5)
    # Clamp between ₹5,000 and ₹5,00,00,000 (5 Cr)
    clamped: float = max(5_000.0, min(raw, 5_00_00_000.0))
    return round(clamped, 2)


def _random_date() -> datetime:
    """Generate a random datetime in the last 90 days."""
    now: datetime = datetime.now()
    delta: timedelta = timedelta(
        days=random.randint(0, 90),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return now - delta


def _generate_risk_score(is_flagged: bool) -> float | None:
    """
    Generate a risk score.
    • Flagged transactions skew 60–100.
    • Non-flagged transactions skew 0–50.
    • ~10 % of all records return None (missing).
    """
    if random.random() < 0.10:
        return None  # Intentionally missing

    if is_flagged:
        return round(random.uniform(60.0, 100.0), 1)
    return round(random.uniform(0.0, 50.0), 1)


def _risk_level_from_score(score: float | None) -> RiskLevel | None:
    """Derive categorical risk level from a numeric score."""
    if score is None:
        return None
    if score >= 80:
        return RiskLevel.CRITICAL
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 35:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _generate_single_transaction(index: int) -> dict[str, Any]:
    """
    Build a single transaction dict.

    Approximately 30 % of transactions are flagged to ensure
    the SAR report has meaningful content to analyse.
    """
    is_flagged: bool = random.random() < 0.30
    is_pep: bool = random.random() < 0.08  # ~8 % PEP rate

    risk_score: float | None = _generate_risk_score(is_flagged)
    risk_level: RiskLevel | None = _risk_level_from_score(risk_score)

    # Occasionally use a non-INR currency for cross-border flavour
    currency: Currency = (
        random.choice([Currency.USD, Currency.EUR, Currency.GBP, Currency.AED, Currency.SGD])
        if random.random() < 0.15
        else Currency.INR
    )

    txn: dict[str, Any] = {
        "transaction_id": f"TXN-{index:05d}",
        "account_id": f"ACC-{random.randint(10_000_000, 99_999_999)}",
        "customer_name": random.choice(CUSTOMER_NAMES),
        "account_type": random.choice(list(AccountType)).value,
        "branch_code": random.choice(BRANCH_CODES),
        "transaction_type": random.choice(list(TransactionType)).value,
        "amount": _random_amount(),
        "currency": currency.value,
        "transaction_date": _random_date().isoformat(),
        "counterparty_name": random.choice(COUNTERPARTY_NAMES) if random.random() > 0.1 else None,
        "counterparty_account": (
            f"ACC-{random.randint(10_000_000, 99_999_999)}"
            if random.random() > 0.15
            else None
        ),
        "counterparty_bank": random.choice(COUNTERPARTY_BANKS) if random.random() > 0.2 else None,
        "risk_score": risk_score,
        "risk_level": risk_level.value if risk_level else None,
        "is_flagged": is_flagged,
        "flag_reason": random.choice(FLAG_REASONS) if is_flagged else None,
        "is_pep": is_pep,
        "kyc_status": random.choice(KYC_STATUSES),
        "remarks": random.choice(REMARKS_POOL),
    }

    return txn


# ──────────────────────────────────────────────────────────────────────
# Main generation logic
# ──────────────────────────────────────────────────────────────────────

def generate_transaction_batch(
    num_transactions: int = NUM_TRANSACTIONS,
) -> TransactionBatch:
    """
    Generate a batch of synthetic transactions and validate
    them through the Pydantic schema.

    Returns:
        TransactionBatch — fully validated batch ready for pipeline ingestion.

    Raises:
        pydantic.ValidationError — if any generated record fails validation
        (indicates a bug in this generator, not user error).
    """
    raw_transactions: list[dict[str, Any]] = [
        _generate_single_transaction(i + 1) for i in range(num_transactions)
    ]

    batch = TransactionBatch(
        report_id=f"SAR-{datetime.now().strftime('%Y%m%d')}-001",
        reporting_entity="Compliance Division — ABC Financial Services",
        generated_at=datetime.now(),
        transactions=[Transaction(**txn) for txn in raw_transactions],
    )

    return batch


def save_batch_to_json(batch: TransactionBatch, output_path: str | Path) -> Path:
    """
    Serialize a TransactionBatch to a pretty-printed JSON file.

    Args:
        batch: Validated transaction batch.
        output_path: File path for the output JSON.

    Returns:
        Resolved Path of the written file.
    """
    output: Path = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(
            batch.model_dump(mode="json"),
            f,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    return output.resolve()


# ──────────────────────────────────────────────────────────────────────
# CLI Entry Point
# ──────────────────────────────────────────────────────────────────────

def main() -> None:
    """Generate sample data and write to data/sample_transactions.json."""
    random.seed(42)  # Reproducible output

    print("🏦  Generating synthetic financial transaction data...")
    batch: TransactionBatch = generate_transaction_batch()

    output_file: str = os.path.join("data", "sample_transactions.json")
    saved_path: Path = save_batch_to_json(batch, output_file)

    # ── Print summary statistics ─────────────────────────────────
    total: int = len(batch.transactions)
    flagged: int = sum(1 for t in batch.transactions if t.is_flagged)
    missing_risk: int = sum(1 for t in batch.transactions if t.risk_score is None)
    pep_count: int = sum(1 for t in batch.transactions if t.is_pep)
    total_volume: float = sum(t.amount for t in batch.transactions)

    print(f"✅  Generated {total} transactions → {saved_path}")
    print(f"    ├── Flagged:        {flagged} ({flagged/total*100:.0f}%)")
    print(f"    ├── Missing risk:   {missing_risk} ({missing_risk/total*100:.0f}%)")
    print(f"    ├── PEP accounts:   {pep_count}")
    print(f"    └── Total volume:   ₹{total_volume:,.2f}")


if __name__ == "__main__":
    main()
