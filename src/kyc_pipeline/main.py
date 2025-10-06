from datetime import datetime
from kyc_pipeline.crew import KYCPipelineCrew
from .crew import KYCPipelineCrew
from tools.ocr import ocr_extract

def run():
    inputs = {
        "doc_id": "KYC-2025-0001",
        #"s3_uri": "s3://incoming/kyc.pdf",
        "s3_uri": "/Users/britta/Documents/workstation/mtech/AgenticAI/kyc_pipeline/test/idcard_john_doe.jpg",
        "org_id": "test-sg",
        "to_email": "applicant@example.com"
    }

    try:
        result = KYCPipelineCrew().crew().kickoff(inputs=inputs)
        ocr_extract(input)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")
