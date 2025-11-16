import importlib
import os
import sys

# Add the src directory to the import path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../src")))

# Dynamically import the lambda_handler module
lambda_handler_module = importlib.import_module("kyc_pipeline.lambda_handler")

# 👇 Point directly to your local test file
local_path = "/Users/britta/Documents/workstation/mtech/kyc_pipeline/test/non-singaporean-kyc-form.pdf"

# Sample S3 event payload (simulating AWS Lambda trigger)
event = {
    "Records": [
        {
            "s3": {
                "bucket": {"name": "kyc-input-bucket"},
                "object": {"key": local_path}
            }
        }
    ]
}

if __name__ == "__main__":
    result = lambda_handler_module.lambda_handler(event, None)
    print("\n✅ Lambda Result:\n", result)
