import json, os
from crewai.tools import tool
import pytesseract
from PIL import Image
import cv2

@tool("ocr_extract")
def ocr_extract(s3_uri: str) -> str:
    """Extract raw text from a document at s3_uri. (Stub for demo)."""
    """Extract text from an image using Tesseract OCR.
    Supports PNG, JPG, TIFF, PDF (if converted to image)."""
    image_path = s3_uri
    # Load image with OpenCV for preprocessing
    image = cv2.imread(image_path)

    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Optional: apply thresholding for better OCR on noisy scans
    gray = cv2.threshold(gray, 0, 255,
                         cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]

    # Save temp processed file
    temp_filename = "temp.png"
    cv2.imwrite(temp_filename, gray)

    # Run Tesseract OCR
    text = pytesseract.image_to_string(Image.open(temp_filename))

    return text

# if __name__ == "__main__":
#     path = "./test/idcard_john_doe.jpg"
#     raw_text = extract_text(path)
#     print("🔎 OCR Extracted Text:")
#     print(raw_text)
