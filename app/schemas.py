from typing import List, Optional, Literal
from pydantic import BaseModel, Field

class TransactionItem(BaseModel):
    id: str = Field(description="Sequential identifier like tx_001")
    date: str = Field(description="Transaction date formatted as YYYY-MM-DD")
    description: str = Field(description="Clean transaction narrative")
    transaction_type: Literal["DEBIT", "CREDIT"] = Field(description="DEBIT or CREDIT")
    amount: float = Field(description="Positive numerical transaction value")
    running_balance: Optional[float] = Field(default=None, description="Account balance following transaction if present")

class StatementSummary(BaseModel):
    account_number_masked: Optional[str] = Field(default=None, description="Masked account string (e.g., ****4892)")
    opening_balance: float = Field(description="Starting account balance")
    total_deposits: float = Field(description="Total credits/deposits sum")
    total_withdrawals: float = Field(description="Total debits/withdrawals sum")
    closing_balance: float = Field(description="Ending account balance")

class BankStatementExtract(BaseModel):
    summary: StatementSummary
    transactions: List[TransactionItem]