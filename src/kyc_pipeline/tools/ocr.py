import json, os
from crewai.tools import tool
from pathlib import Path

_STUBS = {
    # filename → normalized fields you want your Extract step to use
    "idcard_john_doe.jpg": {
        "name": "JOHN DOE",
        "dob": "1990-01-01",
        "address": "123 Example St, #01-01, Singapore 123456",
        "id_number": "S1234567A",
        "has_face_photo": True,
        "confidence": 0.95,
        "coverage_notes": "Stubbed OCR output"
    },
    # add more test files here if needed
}

def _stub_payload_for(uri: str):
    fname = Path(uri).name
    return _STUBS.get(fname, {
        # fall-back stub (useful even when filename doesn’t match)
        "name": "ADA LOVELACE",
        "dob": "1815-12-10",
        "address": "10 Bayes Rd, London",
        "id_number": "SG1234567",
        "has_face_photo": True,
        "confidence": 0.9,
        "coverage_notes": "Global fallback stub"
    })

def ocr_extract_pure(s3_uri: str) -> str:
    """
    Return OCR result as a JSON string with normalized keys.
    In stub mode (OCR_MODE=stub), return canned data based on file name.
    """
    mode = os.getenv("OCR_MODE", "real").lower()

    if mode == "stub":
        payload = _stub_payload_for(s3_uri)
        return json.dumps({"extracted": payload})  # JSON STRING

    # --- real mode (placeholder) ---
    # text = run_real_ocr(s3_uri)
    # parsed = parse_text_to_fields(text)
    # return json.dumps({"extracted": parsed})
    return json.dumps({"extracted": _stub_payload_for(s3_uri)})  # temporary until real OCR wired
ocr_extract = tool("ocr_extract")(ocr_extract_pure)
