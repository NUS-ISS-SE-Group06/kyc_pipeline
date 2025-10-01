from datetime import datetime
from kyc_pipeline.crew import KYCPipelineCrew

def run():
    inputs = {
        "doc_id": "KYC-2025-0001",
        #"s3_uri": "s3://incoming/kyc.pdf",
        "s3_uri": "/Users/balajisivaprakasam/nus/kyc_pipeline/test/idcard_john_doe.jpg",
        "org_id": "test-sg",
        "to_email": "applicant@example.com"
    }

    try:
        result = KYCPipelineCrew().crew().kickoff(inputs=inputs)
    except Exception as e:
        raise Exception(f"An error occurred while running the crew: {e}")
