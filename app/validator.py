from typing import Dict, Any, List
from app.schemas import BankStatementExtract

def reconcile_statement_math(extracted: BankStatementExtract) -> Dict[str, Any]:
    summary = extracted.summary
    transactions = extracted.transactions
    
    computed_deposits = sum(tx.amount for tx in transactions if tx.transaction_type == "CREDIT")
    computed_withdrawals = sum(tx.amount for tx in transactions if tx.transaction_type == "DEBIT")
    
    expected_closing = round(summary.opening_balance + summary.total_deposits - summary.total_withdrawals, 2)
    actual_closing = round(summary.closing_balance, 2)
    
    math_valid = abs(expected_closing - actual_closing) <= 0.02
    validation_flags: List[str] = []
    
    if not math_valid:
        validation_flags.append(
            f"SUMMARY_MATH_MISMATCH: Computed ending balance ({expected_closing}) != statement value ({actual_closing})"
        )
        
    if round(computed_deposits, 2) != round(summary.total_deposits, 2):
        validation_flags.append(
            f"DEPOSIT_SUM_MISMATCH: Transaction sum ({round(computed_deposits, 2)}) != summary ({summary.total_deposits})"
        )

    if round(computed_withdrawals, 2) != round(summary.total_withdrawals, 2):
        validation_flags.append(
            f"WITHDRAWAL_SUM_MISMATCH: Transaction sum ({round(computed_withdrawals, 2)}) != summary ({summary.total_withdrawals})"
        )

    return {
        "status": "VALIDATED" if not validation_flags else "FLAGGED",
        "validation_flags": validation_flags,
        "metrics": {
            "computed_deposits": round(computed_deposits, 2),
            "computed_withdrawals": round(computed_withdrawals, 2)
        }
    }