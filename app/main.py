from fastapi import FastAPI, UploadFile, File
from app.extractor import extract_raw_pdf_text, parse_pdf_with_llm

app = FastAPI(
    title="Enterprise Financial Document Extraction API",
    version="6.5.2"
)

@app.get("/")
def root():
    return {"status": "online", "version": "6.5.2"}

# --- ADD THIS BANK STATEMENT ENDPOINT ---
@app.post("/v1/parse/statement")
async def parse_bank_statement(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    result = parse_pdf_with_llm(raw_text)
    return result

# --- YOUR EXISTING ROUTES ---
@app.post("/v1/parse/w2")
async def parse_w2(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    result = parse_pdf_with_llm(raw_text)
    return result

@app.post("/v1/parse/sec-10k")
async def parse_sec_10k(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    result = parse_pdf_with_llm(raw_text)
    return result
