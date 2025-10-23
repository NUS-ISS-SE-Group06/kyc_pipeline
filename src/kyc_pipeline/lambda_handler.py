import json
import os
from kyc_pipeline.main import KYCPipelineCrew  # or directly from .crew if defined there

def lambda_handler(event, context):
    print("S3 event:", json.dumps(event))
    record = event['Records'][0]
    bucket = record['s3']['bucket']['name']
    key = record['s3']['object']['key']

    # ✅ Use local path directly if it exists
    if os.path.exists(key):
        print(f"📂 Local file detected: {key}")
        s3_uri = key
    else:
        s3_uri = f"s3://{bucket}/{key.lstrip('/')}"
        print(f"🪣 Using S3 URI: {s3_uri}")

    doc_id = os.path.basename(key)
    doc_type = "ID_CARD"

    crew = KYCPipelineCrew().crew()
    result = crew.kickoff(inputs={"s3_uri": s3_uri, "doc_id": doc_id, "doc_type": doc_type})

    return {
        "statusCode": 200,
        "body": json.dumps({"message": "KYC decision processed", "result": result})
    }
