import re
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
import fitz  # PyMuPDF


# ------------------------------------------------------------------
# Pydantic Schemas
# ------------------------------------------------------------------

class StatementSummary(BaseModel):
    opening_balance: Optional[float] = Field(None, description="Starting account balance")
    total_deposits: Optional[float] = Field(None, description="Sum of incoming credits/deposits")
    total_withdrawals: Optional[float] = Field(None, description="Sum of outgoing debits/withdrawals")
    ending_balance: Optional[float] = Field(None, description="Reported ending account balance")


class MathReconciliation(BaseModel):
    calculated_ending_balance: Optional[float] = Field(None, description="Opening + Deposits - Withdrawals")
    discrepancy: float = Field(0.0, description="Difference between calculated and reported balance")
    is_reconciled: bool = Field(False, description="True if discrepancy is zero")


class TransactionAudit(BaseModel):
    calculated_deposits: float = Field(0.0, description="Sum of positive transaction line items")
    calculated_withdrawals: float = Field(0.0, description="Sum of negative transaction line items")
    deposits_discrepancy: float = Field(0.0, description="|Total Deposits - Calculated Deposits|")
    withdrawals_discrepancy: float = Field(0.0, description="|Total Withdrawals - Calculated Withdrawals|")
    transactions_reconciled: bool = Field(False, description="True if line items match summary totals")


class Transaction(BaseModel):
    date: str = Field(..., description="Transaction date")
    description: str = Field(..., description="Transaction merchant or line narrative")
    amount: float = Field(..., description="Transaction amount")


class StatementData(BaseModel):
    account_number: str
    statement_period: str
    summary: StatementSummary
    reconciliation: MathReconciliation
    transaction_audit: TransactionAudit
    detected_transactions: List[Transaction]


class StatementParseResponse(BaseModel):
    status: str
    parsing_engine: str
    filename: str
    data: StatementData
    raw_text_snippet: str


# ------------------------------------------------------------------
# FastAPI Application & Logic
# ------------------------------------------------------------------

app = FastAPI(
    title="Enterprise Financial Document Extraction API",
    version="6.5.2"
)


def extract_raw_pdf_text(pdf_bytes: bytes) -> str:
    text = ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text


def parse_bank_statement_local(raw_text: str) -> StatementData:
    account_number_match = re.search(r'Account\s*Number:\s*([\*\d\-]+)', raw_text, re.IGNORECASE)
    date_range_match = re.search(r'Statement\s*Period:\s*([^\n\r]+)', raw_text, re.IGNORECASE)
    
    opening_match = re.search(r'Opening\s*Balance:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)
    deposits_match = re.search(r'Total\s*Deposits:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)
    withdrawals_match = re.search(r'Total\s*Withdrawals:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)
    ending_match = re.search(r'Ending\s*Balance:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)

    opening = float(opening_match.group(1).replace(',', '')) if opening_match else None
    deposits = float(deposits_match.group(1).replace(',', '')) if deposits_match else None
    withdrawals = float(withdrawals_match.group(1).replace(',', '')) if withdrawals_match else None
    ending = float(ending_match.group(1).replace(',', '')) if ending_match else None

    # Summary balance reconciliation
    reconciliation = MathReconciliation(calculated_ending_balance=None, discrepancy=0.0, is_reconciled=False)
    if None not in (opening, deposits, withdrawals, ending):
        calc_ending = round(opening + deposits - withdrawals, 2)
        discrepancy = round(abs(calc_ending - ending), 2)
        reconciliation = MathReconciliation(
            calculated_ending_balance=calc_ending,
            discrepancy=discrepancy,
            is_reconciled=(discrepancy < 0.01)
        )

    # Line item extraction & audit accumulation
    lines = raw_text.split('\n')
    transactions = []
    transaction_pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\s+(.*?)\s+\$?(-?[\d,]+\.\d{2})'
    )
    
    sum_credits = 0.0
    sum_debits = 0.0

    for line in lines:
        match = transaction_pattern.search(line.strip())
        if match:
            amount = float(match.group(3).replace(',', ''))
            transactions.append(Transaction(
                date=match.group(1),
                description=match.group(2).strip(),
                amount=amount
            ))
            
            if amount > 0:
                sum_credits += amount
            else:
                sum_debits += abs(amount)

    sum_credits = round(sum_credits, 2)
    sum_debits = round(sum_debits, 2)

    dep_disc = round(abs((deposits or 0.0) - sum_credits), 2)
    with_disc = round(abs((withdrawals or 0.0) - sum_debits), 2)

    transaction_audit = TransactionAudit(
        calculated_deposits=sum_credits,
        calculated_withdrawals=sum_debits,
        deposits_discrepancy=dep_disc,
        withdrawals_discrepancy=with_disc,
        transactions_reconciled=(dep_disc < 0.01 and with_disc < 0.01)
    )

    return StatementData(
        account_number=account_number_match.group(1) if account_number_match else "Not Found",
        statement_period=date_range_match.group(1).strip() if date_range_match else "Not Found",
        summary=StatementSummary(
            opening_balance=opening,
            total_deposits=deposits,
            total_withdrawals=withdrawals,
            ending_balance=ending
        ),
        reconciliation=reconciliation,
        transaction_audit=transaction_audit,
        detected_transactions=transactions
    )


@app.get("/")
def root():
    return {"status": "online", "version": "6.5.2", "mode": "local_pymupdf"}


@app.post("/v1/parse/statement", response_model=StatementParseResponse)
async def parse_statement(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        raw_text = extract_raw_pdf_text(pdf_bytes)
        structured_data = parse_bank_statement_local(raw_text)
        
        return StatementParseResponse(
            status="success",
            parsing_engine="PyMuPDF_Regex_Pydantic_Local",
            filename=file.filename,
            data=structured_data,
            raw_text_snippet=raw_text[:300] + "..." if len(raw_text) > 300 else raw_text
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Local Processing Error: {str(e)}")


@app.post("/v1/parse/w2")
async def parse_w2(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    return {"status": "success", "parsing_engine": "PyMuPDF_Local", "doc_type": "W-2", "raw_text_snippet": raw_text[:500]}


@app.post("/v1/parse/sec-10k")
async def parse_sec_10k(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    return {"status": "success", "parsing_engine": "PyMuPDF_Local", "doc_type": "SEC-10K", "raw_text_snippet": raw_text[:500]}
