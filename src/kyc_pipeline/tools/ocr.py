import json, os
from crewai.tools import tool
import pytesseract
import re  
from PIL import Image
import cv2
import magic

ALLOWED_MIME_TYPES = ["image/jpeg", "image/png", "image/tiff", "application/pdf"]
MAX_FILE_SIZE_MB = 10  # Limit file size


@tool("ocr_extract")
def ocr_extract(s3_uri: str) -> str:
    """
    Extract text from an image or PDF using Tesseract OCR,
    after validating file safety and content integrity.
    """
    image_path = s3_uri

    # 1️⃣ Validate file exists and size
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"❌ File not found: {image_path}")

    file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
    if file_size_mb > MAX_FILE_SIZE_MB:
        raise ValueError(f"❌ File too large ({file_size_mb:.2f} MB). Limit is {MAX_FILE_SIZE_MB} MB.")

    # 2️⃣ Validate MIME type
    mime = magic.Magic(mime=True)
    mime_type = mime.from_file(image_path)
    if mime_type not in ALLOWED_MIME_TYPES:
        raise ValueError(f"❌ Unsupported file type: {mime_type}")

    # 3️⃣ Load image
    image = cv2.imread(image_path)
    if image is None:
        raise ValueError("❌ Unable to read image (possibly corrupted).")

    # 4️⃣ Preprocess
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    temp_filename = "temp.png"
    cv2.imwrite(temp_filename, gray)

    # 5️⃣ Run OCR
    text = pytesseract.image_to_string(Image.open(temp_filename))

    # 6️⃣ Validate OCR text safety
    safe_text = validate_ocr_text_safety(text)

    print("✅ File validated, sanitized, and OCR completed successfully.")
    return safe_text

# 🔒 Separate malicious content validator
def validate_ocr_text_safety(text: str) -> None:
    """
    Validate OCR-extracted text for malicious or unsafe content.
    Raises ValueError if unsafe patterns are detected.
    """
    # Suspicious patterns that may indicate prompt injection or malicious commands
    suspicious_patterns = [
        r"<script.*?>", r"</script>",                # HTML/JS injection
        r"(?i)system\(", r"(?i)os\.system",          # Python/system exec
        r"(?i)subprocess", r"(?i)eval\(",            # Code execution
        r"(?i)bash", r"(?i)cmd\.exe",                # Shell commands
        r"(?i)rm\s+-rf", r"(?i)del\s+",              # File deletion
        r"(?i)curl\s+http", r"(?i)wget\s+http",      # Remote fetch
        r"(?i)base64\s+decode",                      # Encoded payloads
        r"(?i)import\s+os", r"(?i)import\s+sys"      # Python injections
    ]

    for pattern in suspicious_patterns:
        if re.search(pattern, text):
            raise ValueError(f"⚠️ Malicious content detected: pattern '{pattern}'")

    # Clean up control or invisible characters
    sanitized = re.sub(r"[\x00-\x1F\x7F]", "", text)
    sanitized = re.sub(r"[ \t]+", " ", text)
    sanitized = sanitized.strip()
    return sanitized

