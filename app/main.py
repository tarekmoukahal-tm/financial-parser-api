from fastapi import FastAPI, UploadFile, File, HTTPException, status
import uuid
import time
from app.extractor import extract_raw_pdf_text, parse_pdf_with_llm
from app.validator import reconcile_statement_math

app = FastAPI(
    title="Financial Statement Parsing API",
    version="1.0.0",
    description="Synchronous PDF financial statement extraction and math validation."
)

@app.get("/healthz", status_code=status.HTTP_200_OK)
async def health_check():
    return {"status": "healthy", "timestamp": time.time()}

@app.post("/v1/parse/statement")
async def parse_statement(file: UploadFile = File(...)):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="Invalid file type. Only PDF documents are supported."
        )
        
    start_time = time.time()
    file_bytes = await file.read()
    
    try:
        raw_text = extract_raw_pdf_text(file_bytes)
        extracted_data = parse_pdf_with_llm(raw_text)
        reconciliation = reconcile_statement_math(extracted_data)
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        return {
            "request_id": f"req_{uuid.uuid4()}",
            "processing_time_ms": processing_time_ms,
            "data": extracted_data.model_dump(),
            "reconciliation": reconciliation
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Parsing execution failed: {str(e)}"
        )