import os
import json
import pytest
from kyc_pipeline.tools.ocr import ocr_extract_pure

def test_ocr_extract_text_stub_json(monkeypatch: pytest.MonkeyPatch):
    # Ensure stub path is used
    monkeypatch.setenv("OCR_MODE", "stub")

    uri = "s3://bucket/folder/sample-id.pdf"
    out = ocr_extract_pure(uri)          # returns JSON string
    data = json.loads(out)               # parse JSON
    extracted = data["extracted"]

    # Name exists (case-insensitive check to match your expectation)
    assert extracted["name"].lower() == "ada lovelace"

    # ID number field check (your expectation was "ID: SG1234567")
    # Here we assert on canonical field instead:
    assert extracted["id_number"] == "SG1234567"
