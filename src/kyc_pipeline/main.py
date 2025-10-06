from datetime import datetime
from kyc_pipeline.crew import KYCPipelineCrew
from kyc_pipeline.tools.ocr import ocr_extract


def run():
    inputs = {
        "doc_id": "KYC-2025-0001",
        #"s3_uri": "s3://incoming/kyc.pdf",
        "s3_uri": "/Users/britta/Documents/workstation/mtech/AgenticAI/kyc_pipeline/test/idcard_john_doe.jpg",
        "doc_type": "KYC",
        "to_email": "applicant@example.com"

    }

    try:
        # Run the Crew pipeline
        result = KYCPipelineCrew().crew().kickoff(inputs=inputs)
        print("🚀 Crew pipeline result:", result)

         # Run OCR on the document
        ocr_text = ocr_extract(inputs["s3_uri"])
        print("🧾 OCR Extracted Text:\n", ocr_text)

    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")
