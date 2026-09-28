import re
from fastapi import FastAPI, UploadFile, File, HTTPException
import fitz  # PyMuPDF

app = FastAPI(
    title="Enterprise Financial Document Extraction API",
    version="6.5.2"
)

def extract_raw_pdf_text(pdf_bytes: bytes) -> str:
    """Extracts raw text from uploaded PDF bytes using PyMuPDF."""
    text = ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text

def parse_bank_statement_local(raw_text: str) -> dict:
    """Extracts key statement metrics and transactions using regular expressions."""
    # Simple regex patterns for common bank statement fields
    account_number_match = re.search(r'(?:Account|Acc)\s*#?:?\s*(\d+[\d\-]+)', raw_text, re.IGNORECASE)
    date_range_match = re.search(r'(?:Statement Period|Date):\s*([A-Za-z0-9\s,\-/]+)', raw_text, re.IGNORECASE)
    
    # Extract numeric values formatted as currency ($X,XXX.XX)
    amounts = re.findall(r'\$?\b\d{1,3}(?:,\d{3})*\.\d{2}\b', raw_text)
    
    # Extract line items looking like: MM/DD Description $Amount
    lines = raw_text.split('\n')
    transactions = []
    transaction_pattern = re.compile(r'(\d{1,2}/\d{1,2}(?:/\d{2,4})?)\s+(.*?)\s+\$?(-?\d{1,3}(?:,\d{3})*\.\d{2})')
    
    for line in lines:
        match = transaction_pattern.search(line.strip())
        if match:
            transactions.append({
                "date": match.group(1),
                "description": match.group(2).strip(),
                "amount": match.group(3)
            })

    return {
        "account_number": account_number_match.group(1) if account_number_match else "Not Found",
        "statement_period": date_range_match.group(1).strip() if date_range_match else "Not Found",
        "extracted_amounts_found": len(amounts),
        "detected_transactions": transactions,
        "sample_amounts": amounts[:5]
    }

@app.get("/")
def root():
    return {"status": "online", "version": "6.5.2", "mode": "local_pymupdf"}

@app.post("/v1/parse/statement")
async def parse_statement(file: UploadFile = File(...)):
    try:
        pdf_bytes = await file.read()
        raw_text = extract_raw_pdf_text(pdf_bytes)
        structured_data = parse_bank_statement_local(raw_text)
        
        return {
            "status": "success",
            "parsing_engine": "PyMuPDF_Regex_Local",
            "filename": file.filename,
            "data": structured_data,
            "raw_text_snippet": raw_text[:300] + "..." if len(raw_text) > 300 else raw_text
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Local PDF Processing Error: {str(e)}")

@app.post("/v1/parse/w2")
async def parse_w2(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    return {
        "status": "success",
        "parsing_engine": "PyMuPDF_Local",
        "doc_type": "W-2",
        "raw_text_snippet": raw_text[:500]
    }

@app.post("/v1/parse/sec-10k")
async def parse_sec_10k(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    return {
        "status": "success",
        "parsing_engine": "PyMuPDF_Local",
        "doc_type": "SEC-10K",
        "raw_text_snippet": raw_text[:500]
    }
