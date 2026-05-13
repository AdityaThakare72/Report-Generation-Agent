"""
src/models.py
─────────────
Pydantic v2 schemas for financial transaction data used in the
AI Compliance Monitoring — Suspicious Activity Report (SAR) pipeline.

These models enforce strict data validation at the ingestion boundary
(Node 1 — Field Mapper) and define the canonical field names used
throughout the LangGraph pipeline.

Regulatory context:
    • RBI Master Direction – KYC (Know Your Customer) norms
    • SEBI Circular on Anti-Money-Laundering Standards
    • FATF Suspicious Transaction Reporting guidelines
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


# ──────────────────────────────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────────────────────────────

class TransactionType(str, enum.Enum):
    """Classification of financial transaction types."""
    WIRE_TRANSFER = "wire_transfer"
    CASH_DEPOSIT = "cash_deposit"
    CASH_WITHDRAWAL = "cash_withdrawal"
    CHEQUE = "cheque"
    RTGS = "rtgs"
    NEFT = "neft"
    UPI = "upi"
    FOREX = "forex"
    INTERNAL_TRANSFER = "internal_transfer"


class RiskLevel(str, enum.Enum):
    """Risk classification for a transaction or entity."""
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class AccountType(str, enum.Enum):
    """Type of bank account."""
    SAVINGS = "savings"
    CURRENT = "current"
    NRE = "nre"
    NRO = "nro"
    CORPORATE = "corporate"


class Currency(str, enum.Enum):
    """Supported ISO 4217 currency codes."""
    INR = "INR"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    AED = "AED"
    SGD = "SGD"


# ──────────────────────────────────────────────────────────────────────
# Core Transaction Schema
# ──────────────────────────────────────────────────────────────────────

class Transaction(BaseModel):
    """
    A single financial transaction record.

    Fields are aligned with RBI STR (Suspicious Transaction Report)
    and SEBI AML reporting requirements.
    """

    # ── Identifiers ──────────────────────────────────────────────────
    transaction_id: str = Field(
        ...,
        min_length=1,
        description="Unique identifier for the transaction (e.g., TXN-00001).",
    )
    account_id: str = Field(
        ...,
        min_length=1,
        description="Bank account number or internal account identifier.",
    )
    customer_name: str = Field(
        ...,
        min_length=1,
        description="Full name of the account holder.",
    )

    # ── Account metadata ─────────────────────────────────────────────
    account_type: AccountType = Field(
        ...,
        description="Type of bank account (savings, current, NRE, etc.).",
    )
    branch_code: str = Field(
        ...,
        min_length=1,
        description="Branch IFSC or internal branch code.",
    )

    # ── Transaction details ──────────────────────────────────────────
    transaction_type: TransactionType = Field(
        ...,
        description="Nature of the transaction.",
    )
    amount: float = Field(
        ...,
        gt=0,
        description="Transaction amount (must be > 0).",
    )
    currency: Currency = Field(
        default=Currency.INR,
        description="ISO 4217 currency code.",
    )
    transaction_date: datetime = Field(
        ...,
        description="Timestamp of the transaction (ISO 8601).",
    )

    # ── Counterparty ─────────────────────────────────────────────────
    counterparty_name: Optional[str] = Field(
        default=None,
        description="Name of the receiving/sending party, if known.",
    )
    counterparty_account: Optional[str] = Field(
        default=None,
        description="Account identifier of the counterparty.",
    )
    counterparty_bank: Optional[str] = Field(
        default=None,
        description="Name or IFSC of the counterparty's bank.",
    )

    # ── Risk indicators ──────────────────────────────────────────────
    risk_score: Optional[float] = Field(
        default=None,
        ge=0.0,
        le=100.0,
        description="ML-derived risk score (0–100). May be missing.",
    )
    risk_level: Optional[RiskLevel] = Field(
        default=None,
        description="Categorical risk level. Derived from risk_score or assigned by Node 3.",
    )
    is_flagged: bool = Field(
        default=False,
        description="Whether the transaction has been flagged by the AML engine.",
    )
    flag_reason: Optional[str] = Field(
        default=None,
        description="Human-readable reason for the flag.",
    )

    # ── KYC / PEP ────────────────────────────────────────────────────
    is_pep: bool = Field(
        default=False,
        description="Is the customer a Politically Exposed Person?",
    )
    kyc_status: Optional[str] = Field(
        default=None,
        description="KYC verification status (e.g., 'Verified', 'Pending', 'Expired').",
    )

    # ── Additional context ───────────────────────────────────────────
    remarks: Optional[str] = Field(
        default=None,
        description="Free-text remarks from the compliance officer.",
    )

    # ── Validators ───────────────────────────────────────────────────

    @field_validator("transaction_id")
    @classmethod
    def validate_transaction_id(cls, v: str) -> str:
        """Ensure transaction IDs follow the expected format."""
        if not v.startswith("TXN-"):
            raise ValueError(
                f"transaction_id must start with 'TXN-', got '{v}'"
            )
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "transaction_id": "TXN-00001",
                "account_id": "ACC-10234567",
                "customer_name": "Rajesh Kumar Sharma",
                "account_type": "savings",
                "branch_code": "HDFC0001234",
                "transaction_type": "wire_transfer",
                "amount": 1500000.00,
                "currency": "INR",
                "transaction_date": "2026-05-10T14:30:00",
                "counterparty_name": "Offshore Holdings Ltd",
                "counterparty_account": "ACC-99887766",
                "counterparty_bank": "HSBC0005678",
                "risk_score": 87.5,
                "risk_level": "High",
                "is_flagged": True,
                "flag_reason": "Large outward remittance to high-risk jurisdiction",
                "is_pep": False,
                "kyc_status": "Verified",
                "remarks": "Flagged for manual review — unusual pattern",
            }
        }


# ──────────────────────────────────────────────────────────────────────
# Batch Input Schema
# ──────────────────────────────────────────────────────────────────────

class TransactionBatch(BaseModel):
    """
    A batch of transactions submitted for SAR analysis.

    This is the top-level schema expected by Node 1 (Field Mapper).
    """

    report_id: str = Field(
        ...,
        description="Unique identifier for this SAR processing run.",
    )
    reporting_entity: str = Field(
        default="Compliance Division — ABC Financial Services",
        description="Name of the entity filing the report.",
    )
    generated_at: datetime = Field(
        default_factory=datetime.now,
        description="Timestamp when the batch was generated.",
    )
    transactions: list[Transaction] = Field(
        ...,
        min_length=1,
        description="List of transactions to analyse.",
    )


# ──────────────────────────────────────────────────────────────────────
# Regulatory Field Mapping (used by Node 1)
# ──────────────────────────────────────────────────────────────────────

# Maps internal field names → regulatory report field names
# as expected in RBI STR / SEBI AML filings.
REGULATORY_FIELD_MAP: dict[str, str] = {
    "transaction_id": "STR Reference Number",
    "account_id": "Account Number",
    "customer_name": "Name of Account Holder",
    "account_type": "Type of Account",
    "branch_code": "Branch IFSC Code",
    "transaction_type": "Nature of Transaction",
    "amount": "Transaction Amount (₹)",
    "currency": "Currency Code",
    "transaction_date": "Date & Time of Transaction",
    "counterparty_name": "Beneficiary / Remitter Name",
    "counterparty_account": "Beneficiary Account Number",
    "counterparty_bank": "Beneficiary Bank IFSC",
    "risk_score": "Risk Score (0–100)",
    "risk_level": "Risk Classification",
    "is_flagged": "AML Flag Status",
    "flag_reason": "Reason for Flag",
    "is_pep": "PEP Indicator",
    "kyc_status": "KYC Verification Status",
    "remarks": "Officer Remarks",
}
