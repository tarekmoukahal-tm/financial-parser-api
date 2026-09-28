import os
import re
from typing import List, Optional
from fastapi import FastAPI, UploadFile, File, HTTPException
from pydantic import BaseModel, Field
import fitz  # PyMuPDF
from openai import OpenAI


# ------------------------------------------------------------------
# Pydantic Schemas - Bank Statement
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
# Pydantic Schemas - Form W-2
# ------------------------------------------------------------------

class W2EmployerInfo(BaseModel):
    ein: Optional[str] = Field(None, description="Employer Identification Number (EIN)")
    name: Optional[str] = Field(None, description="Employer name")
    address: Optional[str] = Field(None, description="Employer address")


class W2EmployeeInfo(BaseModel):
    ssn: Optional[str] = Field(None, description="Employee Social Security Number")
    name: Optional[str] = Field(None, description="Employee name")
    address: Optional[str] = Field(None, description="Employee address")


class W2WagesAndTaxes(BaseModel):
    wages_tips_compensation: Optional[float] = Field(None, description="Box 1: Wages, tips, other comp.")
    federal_income_tax_withheld: Optional[float] = Field(None, description="Box 2: Federal income tax withheld")
    social_security_wages: Optional[float] = Field(None, description="Box 3: Social security wages")
    social_security_tax_withheld: Optional[float] = Field(None, description="Box 4: Social security tax withheld")
    medicare_wages_and_tips: Optional[float] = Field(None, description="Box 5: Medicare wages and tips")
    medicare_tax_withheld: Optional[float] = Field(None, description="Box 6: Medicare tax withheld")
    social_security_tips: Optional[float] = Field(None, description="Box 7: Social security tips")
    allocated_tips: Optional[float] = Field(None, description="Box 8: Allocated tips")


class W2StateTaxInfo(BaseModel):
    state: Optional[str] = Field(None, description="Box 15: Employer state ID code")
    employer_state_id: Optional[str] = Field(None, description="Box 15: Employer's state ID number")
    state_wages: Optional[float] = Field(None, description="Box 16: State wages, tips, etc.")
    state_income_tax: Optional[float] = Field(None, description="Box 17: State income tax")


class W2Data(BaseModel):
    tax_year: Optional[str] = Field(None, description="Tax Year for the W-2 form")
    employer: W2EmployerInfo
    employee: W2EmployeeInfo
    compensation_and_taxes: W2WagesAndTaxes
    state_tax: Optional[W2StateTaxInfo] = None


class W2ParseResponse(BaseModel):
    status: str
    parsing_engine: str
    filename: str
    data: W2Data
    raw_text_snippet: str


# ------------------------------------------------------------------
# Pydantic Schemas - SEC Form 10-K
# ------------------------------------------------------------------

class SECCompanyHeader(BaseModel):
    company_name: Optional[str] = Field(None, description="Exact registrant company name")
    cik: Optional[str] = Field(None, description="Central Index Key (CIK)")
    fiscal_year_ended: Optional[str] = Field(None, description="Fiscal year end date")
    trading_symbol: Optional[str] = Field(None, description="Ticker symbol if available")


class SECFinancialMetrics(BaseModel):
    total_revenue: Optional[float] = Field(None, description="Total net revenues / sales")
    gross_profit: Optional[float] = Field(None, description="Gross profit")
    operating_income: Optional[float] = Field(None, description="Operating income / loss")
    net_income: Optional[float] = Field(None, description="Net income / loss")
    total_assets: Optional[float] = Field(None, description="Total assets")
    total_liabilities: Optional[float] = Field(None, description="Total liabilities")
    total_stockholders_equity: Optional[float] = Field(None, description="Total stockholders' equity")


class SEC10KData(BaseModel):
    company: SECCompanyHeader
    financials: SECFinancialMetrics
    risk_factors_summary: Optional[str] = Field(None, description="Brief high-level summary of Item 1A Risk Factors")


class SEC10KParseResponse(BaseModel):
    status: str
    parsing_engine: str
    filename: str
    data: SEC10KData
    raw_text_snippet: str


# ------------------------------------------------------------------
# FastAPI Application & Global Setup
# ------------------------------------------------------------------

app = FastAPI(
    title="Enterprise Financial Document Extraction API",
    version="6.6.0"
)

# Initialize OpenAI client if key exists
openai_api_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=openai_api_key) if openai_api_key else None


def extract_raw_pdf_text(pdf_bytes: bytes) -> str:
    """Extracts raw text from uploaded PDF bytes using PyMuPDF."""
    text = ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text


# ------------------------------------------------------------------
# Engine Logic - Bank Statement
# ------------------------------------------------------------------

def run_reconciliation_and_audit(
    account_number: str,
    statement_period: str,
    opening: Optional[float],
    deposits: Optional[float],
    withdrawals: Optional[float],
    ending: Optional[float],
    transactions: List[Transaction]
) -> StatementData:
    reconciliation = MathReconciliation(calculated_ending_balance=None, discrepancy=0.0, is_reconciled=False)
    if None not in (opening, deposits, withdrawals, ending):
        calc_ending = round(opening + deposits - withdrawals, 2)
        discrepancy = round(abs(calc_ending - ending), 2)
        reconciliation = MathReconciliation(
            calculated_ending_balance=calc_ending,
            discrepancy=discrepancy,
            is_reconciled=(discrepancy < 0.01)
        )

    sum_credits = 0.0
    sum_debits = 0.0
    for tx in transactions:
        if tx.amount > 0:
            sum_credits += tx.amount
        else:
            sum_debits += abs(tx.amount)

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
        account_number=account_number,
        statement_period=statement_period,
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


def parse_statement_local_regex(raw_text: str) -> StatementData:
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

    lines = raw_text.split('\n')
    transactions = []
    transaction_pattern = re.compile(
        r'(\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4})\s+(.*?)\s+\$?(-?[\d,]+\.\d{2})'
    )
    
    for line in lines:
        match = transaction_pattern.search(line.strip())
        if match:
            transactions.append(Transaction(
                date=match.group(1),
                description=match.group(2).strip(),
                amount=float(match.group(3).replace(',', ''))
            ))

    return run_reconciliation_and_audit(
        account_number=account_number_match.group(1) if account_number_match else "Not Found",
        statement_period=date_range_match.group(1).strip() if date_range_match else "Not Found",
        opening=opening,
        deposits=deposits,
        withdrawals=withdrawals,
        ending=ending,
        transactions=transactions
    )


def parse_statement_openai(raw_text: str) -> StatementData:
    if not client:
        raise ValueError("OpenAI client not initialized (missing OPENAI_API_KEY).")

    class RawLLMExtraction(BaseModel):
        account_number: str
        statement_period: str
        opening_balance: Optional[float]
        total_deposits: Optional[float]
        total_withdrawals: Optional[float]
        ending_balance: Optional[float]
        transactions: List[Transaction]

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract structured financial metrics and transaction line items from the bank statement text."},
            {"role": "user", "content": raw_text}
        ],
        response_format=RawLLMExtraction,
        temperature=0.0
    )

    llm_data = completion.choices[0].message.parsed

    return run_reconciliation_and_audit(
        account_number=llm_data.account_number,
        statement_period=llm_data.statement_period,
        opening=llm_data.opening_balance,
        deposits=llm_data.total_deposits,
        withdrawals=llm_data.total_withdrawals,
        ending=llm_data.ending_balance,
        transactions=llm_data.transactions
    )


# ------------------------------------------------------------------
# Engine Logic - Form W-2
# ------------------------------------------------------------------

def parse_w2_local_regex(raw_text: str) -> W2Data:
    tax_year_match = re.search(r'Form\s*W-2\s*(\d{4})', raw_text, re.IGNORECASE)
    ein_match = re.search(r'Employer\s*identification\s*number\s*\(EIN\):\s*([\d\-]+)', raw_text, re.IGNORECASE)
    ssn_match = re.search(r'Social\s*security\s*number:\s*([\d\-]+)', raw_text, re.IGNORECASE)

    wages_match = re.search(r'1\s*Wages,\s*tips,\s*other\s*comp\.\:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)
    fed_tax_match = re.search(r'2\s*Federal\s*income\s*tax\s*withheld:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)
    ss_wages_match = re.search(r'3\s*Social\s*security\s*wages:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)
    ss_tax_match = re.search(r'4\s*Social\s*security\s*tax\s*withheld:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)
    med_wages_match = re.search(r'5\s*Medicare\s*wages\s*and\s*tips:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)
    med_tax_match = re.search(r'6\s*Medicare\s*tax\s*withheld:\s*\$?([\d,]+\.\d{2})', raw_text, re.IGNORECASE)

    def to_float(match):
        return float(match.group(1).replace(',', '')) if match else None

    return W2Data(
        tax_year=tax_year_match.group(1) if tax_year_match else None,
        employer=W2EmployerInfo(
            ein=ein_match.group(1) if ein_match else None,
            name="Extracted via Local Parser",
            address=None
        ),
        employee=W2EmployeeInfo(
            ssn=ssn_match.group(1) if ssn_match else None,
            name="Extracted via Local Parser",
            address=None
        ),
        compensation_and_taxes=W2WagesAndTaxes(
            wages_tips_compensation=to_float(wages_match),
            federal_income_tax_withheld=to_float(fed_tax_match),
            social_security_wages=to_float(ss_wages_match),
            social_security_tax_withheld=to_float(ss_tax_match),
            medicare_wages_and_tips=to_float(med_wages_match),
            medicare_tax_withheld=to_float(med_tax_match)
        )
    )


def parse_w2_openai(raw_text: str) -> W2Data:
    if not client:
        raise ValueError("OpenAI client not initialized (missing OPENAI_API_KEY).")

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract structured Form W-2 tax data from the provided document text."},
            {"role": "user", "content": raw_text}
        ],
        response_format=W2Data,
        temperature=0.0
    )

    return completion.choices[0].message.parsed


# ------------------------------------------------------------------
# Engine Logic - SEC Form 10-K
# ------------------------------------------------------------------

def parse_sec_10k_local_regex(raw_text: str) -> SEC10KData:
    company_match = re.search(r'COMPANY\s*CONFORMED\s*NAME:\s*([^\n\r]+)', raw_text, re.IGNORECASE)
    cik_match = re.search(r'CENTRAL\s*INDEX\s*KEY:\s*(\d+)', raw_text, re.IGNORECASE)
    fy_match = re.search(r'CONFORMED\s*PERIOD\s*OF\s*REPORT:\s*(\d{8}|\d{4}-\d{2}-\d{2})', raw_text, re.IGNORECASE)

    rev_match = re.search(r'(?:Total\s*Revenues?|Net\s*Sales):\s*\$?([\d,]+(?:\.\d{2})?)', raw_text, re.IGNORECASE)
    net_inc_match = re.search(r'Net\s*Income:\s*\$?([\d,]+(?:\.\d{2})?)', raw_text, re.IGNORECASE)

    def to_float(match):
        return float(match.group(1).replace(',', '')) if match else None

    return SEC10KData(
        company=SECCompanyHeader(
            company_name=company_match.group(1).strip() if company_match else "Unknown Company",
            cik=cik_match.group(1) if cik_match else None,
            fiscal_year_ended=fy_match.group(1) if fy_match else None
        ),
        financials=SECFinancialMetrics(
            total_revenue=to_float(rev_match),
            net_income=to_float(net_inc_match)
        ),
        risk_factors_summary="Regex extraction active. OpenAI required for full NLP risk factor summarization."
    )


def parse_sec_10k_openai(raw_text: str) -> SEC10KData:
    if not client:
        raise ValueError("OpenAI client not initialized (missing OPENAI_API_KEY).")

    completion = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract structured corporate metrics and financial data from the SEC Form 10-K filing text."},
            {"role": "user", "content": raw_text[:20000]}  # Window text sample
        ],
        response_format=SEC10KData,
        temperature=0.0
    )

    return completion.choices[0].message.parsed


# ------------------------------------------------------------------
# Endpoints
# ------------------------------------------------------------------

@app.get("/")
def root():
    return {"status": "online", "version": "6.6.0", "mode": "smart_hybrid_fallback"}


@app.post("/v1/parse/statement", response_model=StatementParseResponse)
async def parse_statement(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        raw_text = extract_raw_pdf_text(pdf_bytes)
        
        try:
            structured_data = parse_statement_openai(raw_text)
            engine_used = "OpenAI_gpt-4o-mini"
        except Exception as openai_err:
            structured_data = parse_statement_local_regex(raw_text)
            engine_used = f"PyMuPDF_Regex_Fallback (OpenAI Reason: {str(openai_err)[:100]})"
        
        return StatementParseResponse(
            status="success",
            parsing_engine=engine_used,
            filename=file.filename,
            data=structured_data,
            raw_text_snippet=raw_text[:300] + "..." if len(raw_text) > 300 else raw_text
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Document Processing Error: {str(e)}")


@app.post("/v1/parse/w2", response_model=W2ParseResponse)
async def parse_w2(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        raw_text = extract_raw_pdf_text(pdf_bytes)

        try:
            structured_data = parse_w2_openai(raw_text)
            engine_used = "OpenAI_gpt-4o-mini"
        except Exception as openai_err:
            structured_data = parse_w2_local_regex(raw_text)
            engine_used = f"PyMuPDF_Regex_Fallback (OpenAI Reason: {str(openai_err)[:100]})"

        return W2ParseResponse(
            status="success",
            parsing_engine=engine_used,
            filename=file.filename,
            data=structured_data,
            raw_text_snippet=raw_text[:300] + "..." if len(raw_text) > 300 else raw_text
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"W-2 Processing Error: {str(e)}")


@app.post("/v1/parse/sec-10k", response_model=SEC10KParseResponse)
async def parse_sec_10k(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        raw_text = extract_raw_pdf_text(pdf_bytes)

        try:
            structured_data = parse_sec_10k_openai(raw_text)
            engine_used = "OpenAI_gpt-4o-mini"
        except Exception as openai_err:
            structured_data = parse_sec_10k_local_regex(raw_text)
            engine_used = f"PyMuPDF_Regex_Fallback (OpenAI Reason: {str(openai_err)[:100]})"

        return SEC10KParseResponse(
            status="success",
            parsing_engine=engine_used,
            filename=file.filename,
            data=structured_data,
            raw_text_snippet=raw_text[:300] + "..." if len(raw_text) > 300 else raw_text
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"SEC 10-K Processing Error: {str(e)}")
