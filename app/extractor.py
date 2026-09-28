import fitz  # PyMuPDF
from openai import OpenAI
from app.config import settings
from app.schemas import BankStatementExtract

client = OpenAI(api_key=settings.OPENAI_API_KEY)

def extract_raw_pdf_text(file_bytes: bytes) -> str:
    """Reads PDF directly from memory buffer using layout blocks."""
    doc = fitz.open(stream=file_bytes, filetype="pdf")
    full_text = []
    
    for page_num in range(len(doc)):
        page = doc[page_num]
        text_blocks = page.get_text("blocks")
        page_content = f"--- PAGE {page_num + 1} ---\n"
        for block in text_blocks:
            page_content += block[4] + "\n"
        full_text.append(page_content)
        
    return "\n".join(full_text)

def parse_pdf_with_llm(raw_text: str) -> BankStatementExtract:
    """Invokes OpenAI Structured Outputs enforced against Pydantic schema."""
    system_prompt = (
        "You are an enterprise financial document extraction system. "
        "Extract statement summary values and all transaction line items into the target schema. "
        "Sanitize garbled Unicode artifacts (e.g. \\uFFFD) and standardize dates to YYYY-MM-DD."
    )
    
    response = client.beta.chat.completions.parse(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": raw_text}
        ],
        response_format=BankStatementExtract,
        temperature=0.0
    )
    
    return response.choices[0].message.parsed