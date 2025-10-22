import os
import re
import tempfile
from typing import Optional

from crewai.tools import tool
import pytesseract
from PIL import Image
import cv2

# import the logging tool from your runlog module
from kyc_pipeline.tools.runlog import persist_runlog   # CrewAI Tool object
from datetime import datetime

# --- Optional MIME helpers (graceful fallbacks) ---
_magic = None
try:
    import magic as _magic  # python-magic (needs libmagic)
except Exception:
    _magic = None

_filetype = None
try:
    import filetype as _filetype  # pure-Python signature-based
except Exception:
    _filetype = None

import mimetypes

# --- PDF rendering without system deps (PyMuPDF) ---
try:
    import fitz  # PyMuPDF
except Exception as e:
    fitz = None  # We'll error only if PDF is actually used


ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/tiff", "application/pdf"}
MAX_FILE_SIZE_MB = 10


def _detect_mime(path: str) -> str:
    """Detect MIME using python-magic, else filetype, else mimetypes."""
    # 1) python-magic (best)
    if _magic is not None:
        try:
            m = _magic.Magic(mime=True)
            return m.from_file(path)
        except Exception:
            pass
    # 2) filetype (good)
    if _filetype is not None:
        try:
            kind = _filetype.guess(path)
            if kind is not None and kind.mime:
                return kind.mime
        except Exception:
            pass
    # 3) mimetypes (extension-based)
    mime, _ = mimetypes.guess_type(path)
    return mime or "application/octet-stream"


def _preprocess_for_ocr(img_bgr) -> str:
    """
    Preprocess with OpenCV and run Tesseract. Returns raw OCR text (str).
    """
    # Convert to gray
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    # Otsu binarization
    _, bw = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)

    # Write to a temp PNG for pytesseract (more reliable than passing arrays)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        temp_path = tmp.name
    try:
        cv2.imwrite(temp_path, bw)
        text = pytesseract.image_to_string(Image.open(temp_path))
        return text
    finally:
        try:
            os.remove(temp_path)
        except Exception:
            pass


def _render_pdf_first_page_to_bgr(pdf_path: str):
    """
    Render first page of a PDF to an OpenCV BGR image using PyMuPDF.
    """
    if fitz is None:
        raise RuntimeError(
            "PyMuPDF (pymupdf) is required to handle PDFs. Install with: uv add pymupdf"
        )
    doc = fitz.open(pdf_path)
    if doc.page_count == 0:
        raise ValueError("PDF has no pages.")
    page = doc.load_page(0)
    # 2.0 to get a higher-res raster for better OCR; adjust if needed
    pix = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False) # type: ignore[attr-defined]
    import numpy as np  # numpy comes with opencv wheels

    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
    # PyMuPDF gives RGB; convert to BGR for OpenCV
    img_bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img_bgr


def validate_ocr_text_safety(text: str) -> str:
    """
    Validate OCR-extracted text for malicious or unsafe content.
    Raises ValueError if unsafe patterns are detected.
    Returns sanitized text (str).
    """
    suspicious_patterns = [
        r"<script.*?>", r"</script>",
        r"(?i)system\(", r"(?i)os\.system",
        r"(?i)subprocess", r"(?i)eval\(",
        r"(?i)bash", r"(?i)cmd\.exe",
        r"(?i)rm\s+-rf", r"(?i)del\s+",
        r"(?i)curl\s+http", r"(?i)wget\s+http",
        r"(?i)base64\s+decode",
        r"(?i)import\s+os", r"(?i)import\s+sys",
    ]
    for pattern in suspicious_patterns:
        if re.search(pattern, text):
            raise ValueError(f"Malicious content detected: pattern '{pattern}'")

    # Remove control/invisible chars; collapse spaces
    sanitized = re.sub(r"[\x00-\x1F\x7F]", "", text)
    sanitized = re.sub(r"[ \t]+", " ", sanitized)
    sanitized = sanitized.strip()
    return sanitized

# 🔹 NEW: post-processing to fix OCR misreads
def normalize_ocr_text(text: str) -> str:
    """
    Fix common OCR misreads like $→S, 0→O, |→I, etc.
    """
    corrections = {
        "$": "S",
        "§": "S",
        "0": "O",
        "|": "I",
    }
    for wrong, right in corrections.items():
        text = text.replace(wrong, right)
    return text

@tool("ocr_extract")
def ocr_extract(s3_uri: str) -> str:
    """
    Extract text from an image or PDF using Tesseract OCR,
    after validating file safety and content integrity.
    Accepts a local file path (you can map S3 → local before calling).
    """
    image_path = s3_uri  # treat as local path
    start_time = datetime.utcnow().isoformat()
    try:
        # 1) Existence & size
        if not os.path.exists(image_path):
            raise FileNotFoundError(f"File not found: {image_path}")

        file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
        if file_size_mb > MAX_FILE_SIZE_MB:
            raise ValueError(f"File too large ({file_size_mb:.2f} MB). Limit is {MAX_FILE_SIZE_MB} MB.")

        # 2) MIME type
        mime_type = _detect_mime(image_path)
        if mime_type not in ALLOWED_MIME_TYPES:
            raise ValueError(f"Unsupported file type: {mime_type}")

        # 3) Load → preprocess → OCR
        if mime_type == "application/pdf":
            img_bgr = _render_pdf_first_page_to_bgr(image_path)
        else:
            img_bgr = cv2.imread(image_path)
            if img_bgr is None:
                raise ValueError("Unable to read image (possibly corrupted or unsupported).")

        raw_text = _preprocess_for_ocr(img_bgr)

        # 4) Safety check + sanitize
        safe_text = validate_ocr_text_safety(raw_text)

        # 🔹 Apply normalization step here
        normalized_text = normalize_ocr_text(safe_text)

        # ✅ Persist success log
        persist_runlog.func({
            "context":"OCR_EXTRACT",
            "details":{
                "file_path": image_path,
                "mime_type": mime_type,
                "status": "success",
                "extracted_length": len(normalized_text),
                "started_at": start_time,
                "finished_at": datetime.utcnow().isoformat(),
            },
        })
        print("✅ OCR completed successfully.")
        return {
            "text": normalized_text,
            "mime_type": mime_type,
            "file_size_mb": round(file_size_mb, 2),
            "status": "success",
        }
    except Exception as e:
        # ❌ Persist failure log
        persist_runlog.func({
            "context":"OCR_EXTRACT",
            "details":{
                "file_path": image_path,
                "status": "failed",
                "error": str(e),
                "started_at": start_time,
                "finished_at": datetime.utcnow().isoformat(),
            },
        })
        raise

# Optional bundle for easy import elsewhere
ocr_tools = [ocr_extract, persist_runlog]