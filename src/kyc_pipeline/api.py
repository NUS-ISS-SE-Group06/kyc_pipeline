from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
from .crew import KYCPipelineCrew

app = FastAPI(title="KYC Pipeline API")

class KYCInput(BaseModel):
    doc_id: str
    s3_uri: str
    doc_type: str
    to_email: str

def _kickoff(inputs: dict):
    KYCPipelineCrew().crew().kickoff(inputs=inputs)

@app.post("/run")
def run_pipeline(payload: KYCInput, background: BackgroundTasks):
    background.add_task(_kickoff, payload.model_dump())
    return {"status": "accepted", "inputs": payload.model_dump()}

@app.get("/ping")
def ping():
    return {"pong": True}