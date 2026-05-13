"""
Synthetic financial transaction data generator.

Produces 50 rows of realistic Indian financial transactions for testing
the SAR pipeline. Key properties of the output:
  - ~30% flagged (high-risk) for meaningful SAR content
  - ~10% missing risk_score/kyc_status for imputation testing
  - Log-normal amount distribution (many small, few large)
  - Indian names, IFSC codes, INR-denominated amounts

Usage:
    python -m src.data_generator
"""

from __future__ import annotations

import json
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

NUM_TRANSACTIONS = 50

CUSTOMER_NAMES = [
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

COUNTERPARTY_NAMES = [
    "Offshore Holdings Ltd", "Global Trade FZE",
    "Pinnacle Investments LLC", "Star Exports Pvt Ltd",
    "Diamond Bullion Traders", "Zenith Capital Partners",
    "Crescent Finance Co", "Lotus Shipping Corp",
    "Eagle Remittance Services", "Sapphire Commodities",
    "Phoenix Industries Ltd", "Meridian Consulting Group",
    "Eastern Promise Trading", "Continental Forex Bureau",
    "Alpine Trust Holdings",
]

BRANCH_CODES = [
    "HDFC0001234", "SBIN0005678", "ICIC0009012",
    "UTIB0003456", "KKBK0007890", "PUNB0002345",
    "BARB0006789", "CNRB0001111", "BKID0002222",
    "IOBA0003333",
]

COUNTERPARTY_BANKS = [
    "HSBC0005678", "CITI0001234", "SCBL0009876",
    "DBSS0004321", "BARB0008765", "SBIN0001111",
    "ICIC0002222",
]

FLAG_REASONS = [
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

# Weighted distribution: ~60% Verified, ~20% Pending, ~10% Expired, ~10% None
KYC_STATUSES: list[str | None] = [
    "Verified", "Verified", "Verified", "Verified",
    "Pending", "Pending",
    "Expired",
    None,
]

REMARKS_POOL: list[str | None] = [
    "Flagged for manual review — unusual pattern",
    "Escalated to senior compliance officer",
    "Customer provided supporting documentation",
    "Pending clarification from branch",
    "Cleared after secondary review",
    None, None, None,
]


def _random_amount() -> float:
    """Log-normal distribution: clusters around ₹50K–₹5L, outliers up to ₹2Cr+."""
    raw = random.lognormvariate(mu=12.0, sigma=1.5)
    return round(max(5_000.0, min(raw, 5_00_00_000.0)), 2)


def _random_date() -> datetime:
    now = datetime.now()
    delta = timedelta(
        days=random.randint(0, 90),
        hours=random.randint(0, 23),
        minutes=random.randint(0, 59),
    )
    return now - delta


def _generate_risk_score(is_flagged: bool) -> float | None:
    """Flagged → 60–100, unflagged → 0–50. ~10% return None to test imputation."""
    if random.random() < 0.10:
        return None
    if is_flagged:
        return round(random.uniform(60.0, 100.0), 1)
    return round(random.uniform(0.0, 50.0), 1)


def _risk_level_from_score(score: float | None) -> RiskLevel | None:
    if score is None:
        return None
    if score >= 80:
        return RiskLevel.CRITICAL
    if score >= 60:
        return RiskLevel.HIGH
    if score >= 35:
        return RiskLevel.MEDIUM
    return RiskLevel.LOW


def _build_transaction(index: int) -> dict[str, Any]:
    """Build a single transaction dict. ~30% flagged, ~8% PEP."""
    is_flagged = random.random() < 0.30
    is_pep = random.random() < 0.08
    risk_score = _generate_risk_score(is_flagged)
    risk_level = _risk_level_from_score(risk_score)

    # ~15% non-INR for cross-border variety
    currency = (
        random.choice([Currency.USD, Currency.EUR, Currency.GBP, Currency.AED, Currency.SGD])
        if random.random() < 0.15
        else Currency.INR
    )

    return {
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


def generate_transaction_batch(n: int = NUM_TRANSACTIONS) -> TransactionBatch:
    """Generate and validate a batch of synthetic transactions."""
    raw = [_build_transaction(i + 1) for i in range(n)]
    return TransactionBatch(
        report_id=f"SAR-{datetime.now().strftime('%Y%m%d')}-001",
        reporting_entity="Compliance Division — ABC Financial Services",
        generated_at=datetime.now(),
        transactions=[Transaction(**txn) for txn in raw],
    )


def save_batch_to_json(batch: TransactionBatch, output_path: str | Path) -> Path:
    """Serialize batch to pretty-printed JSON."""
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(batch.model_dump(mode="json"), f, indent=2, ensure_ascii=False, default=str)
    return out.resolve()


def main() -> None:
    random.seed(42)

    print("Generating synthetic transaction data...")
    batch = generate_transaction_batch()

    path = save_batch_to_json(batch, os.path.join("data", "sample_transactions.json"))

    total = len(batch.transactions)
    flagged = sum(1 for t in batch.transactions if t.is_flagged)
    missing = sum(1 for t in batch.transactions if t.risk_score is None)
    pep = sum(1 for t in batch.transactions if t.is_pep)
    volume = sum(t.amount for t in batch.transactions)

    print(f"Generated {total} transactions -> {path}")
    print(f"  Flagged:       {flagged} ({flagged/total*100:.0f}%)")
    print(f"  Missing risk:  {missing} ({missing/total*100:.0f}%)")
    print(f"  PEP accounts:  {pep}")
    print(f"  Total volume:  INR {volume:,.2f}")


if __name__ == "__main__":
    main()
