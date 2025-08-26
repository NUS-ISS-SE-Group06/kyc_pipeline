from .crew import KYCPipelineCrew

def run():
    inputs = {
        "doc_id": "KYC-2025-0001",
        #"s3_uri": "s3://incoming/kyc.pdf",
        "s3_uri": "/Users/nus/kyc_pipeline/test/idcard_john_doe.jpg",
        "org_id": "test-sg",
        "to_email": "applicant@example.com"
    }
    KYCPipelineCrew().crew().kickoff(inputs=inputs)

def train():
    KYCPipelineCrew().crew().train(n_iterations=1, inputs={
        "doc_id": "KYC-2025-0001",
        "s3_uri": "s3://incoming/kyc.pdf",
        "org_id": "test-sg",
        "to_email": "applicant@example.com"
    })

if __name__ == "__main__":
    run()
