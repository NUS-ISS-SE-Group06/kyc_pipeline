from kyc_pipeline.tools.ocr import ocr_extract_pure

def test_ocr_extract_text_stub():
    uri = "s3://bucket/folder/sample-id.pdf"
    out = ocr_extract_pure(uri)
    assert "Ada Lovelace" in out
    assert "ID: SG1234567" in out
