from crewai.tools import tool

def ocr_extract_pure(s3_uri: str) -> str:
    """Extract raw text from a document at s3_uri. (Stub for demo)."""
    # Replace with AWS Textract or other OCR engine in production.
    return "Name: Ada Lovelace\nDOB: 1815-12-10\nAddress: 10 Bayes Rd\nID: SG1234567\nFace: YES"

ocr_extract = tool("ocr_extract")(ocr_extract_pure)