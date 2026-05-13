"""
Pydantic v2 schemas for financial transaction data and regulatory field mappings.

Defines the canonical data contract used throughout the SAR pipeline.
Validation happens at the ingestion boundary (field mapper node).
"""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class TransactionType(str, enum.Enum):
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
    LOW = "Low"
    MEDIUM = "Medium"
    HIGH = "High"
    CRITICAL = "Critical"


class AccountType(str, enum.Enum):
    SAVINGS = "savings"
    CURRENT = "current"
    NRE = "nre"
    NRO = "nro"
    CORPORATE = "corporate"


class Currency(str, enum.Enum):
    """ISO 4217 currency codes supported by the pipeline."""
    INR = "INR"
    USD = "USD"
    EUR = "EUR"
    GBP = "GBP"
    AED = "AED"
    SGD = "SGD"


class Transaction(BaseModel):
    """
    Single financial transaction record, aligned with RBI STR
    and SEBI AML reporting field requirements.
    """

    transaction_id: str = Field(..., min_length=1)
    account_id: str = Field(..., min_length=1)
    customer_name: str = Field(..., min_length=1)
    account_type: AccountType
    branch_code: str = Field(..., min_length=1, description="Branch IFSC or internal code.")

    transaction_type: TransactionType
    amount: float = Field(..., gt=0)
    currency: Currency = Currency.INR
    transaction_date: datetime

    counterparty_name: Optional[str] = None
    counterparty_account: Optional[str] = None
    counterparty_bank: Optional[str] = None

    risk_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    risk_level: Optional[RiskLevel] = None
    is_flagged: bool = False
    flag_reason: Optional[str] = None

    is_pep: bool = False
    kyc_status: Optional[str] = None
    remarks: Optional[str] = None

    @field_validator("transaction_id")
    @classmethod
    def validate_transaction_id(cls, v: str) -> str:
        if not v.startswith("TXN-"):
            raise ValueError(f"transaction_id must start with 'TXN-', got '{v}'")
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


class TransactionBatch(BaseModel):
    """Top-level schema for a batch of transactions submitted for SAR analysis."""

    report_id: str
    reporting_entity: str = "Compliance Division — ABC Financial Services"
    generated_at: datetime = Field(default_factory=datetime.now)
    transactions: list[Transaction] = Field(..., min_length=1)


# Internal field names → regulatory report field names (RBI STR / SEBI AML)
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
