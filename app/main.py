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

parse_bank_statement_local

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
