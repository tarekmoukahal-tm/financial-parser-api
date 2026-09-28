import os
from fastapi import FastAPI, UploadFile, File, HTTPException
import fitz  # PyMuPDF
from openai import OpenAI

app = FastAPI(
    title="Enterprise Financial Document Extraction API",
    version="6.5.2"
)

# Initialize OpenAI Client (reads OPENAI_API_KEY from environment variables)
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))


def extract_raw_pdf_text(pdf_bytes: bytes) -> str:
    """Extracts plain text content from uploaded PDF bytes using PyMuPDF."""
    text = ""
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        for page in doc:
            text += page.get_text()
    return text


def parse_pdf_with_llm(raw_text: str, doc_type: str) -> dict:
    """Sends raw PDF text to OpenAI gpt-4o-mini for structured JSON extraction."""
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(
            status_code=500, 
            detail="OPENAI_API_KEY environment variable is missing on Render."
        )

    prompt = f"You are a financial document parsing engine. Extract structured data for a {doc_type} from the following text:\n\n{raw_text}"
    
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": "Extract and return clean structured JSON format."},
            {"role": "user", "content": prompt}
        ],
        temperature=0.0
    )
    return {"status": "success", "extracted_data": response.choices[0].message.content}


@app.get("/")
def root():
    return {"status": "online", "version": "6.5.2"}


@app.post("/v1/parse/statement")
async def parse_statement(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    result = parse_pdf_with_llm(raw_text, doc_type="Bank Statement")
    return result


@app.post("/v1/parse/w2")
async def parse_w2(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    result = parse_pdf_with_llm(raw_text, doc_type="IRS Form W-2")
    return result


@app.post("/v1/parse/sec-10k")
async def parse_sec_10k(file: UploadFile = File(...)):
    pdf_bytes = await file.read()
    raw_text = extract_raw_pdf_text(pdf_bytes)
    result = parse_pdf_with_llm(raw_text, doc_type="SEC Form 10-K")
    return result
