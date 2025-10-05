from fastapi import FastAPI, BackgroundTasks, HTTPException, Query
from pydantic import BaseModel
from pathlib import Path
from typing import Optional, List
from datetime import datetime
import json
import os
from dotenv import load_dotenv
from .crew import KYCPipelineCrew

# Load environment variables
load_dotenv()

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

@app.get("/kyc_status")
def get_kyc_status(
        final_decision: Optional[str] = Query(None, description="Filter by decision: PROCESSED, INPROCESS, FAILED"),
        customer_name: Optional[str] = Query(None, description="Search by customer name (case-insensitive)"),
        identification_no: Optional[str] = Query(None, description="Filter by identification number"),
        from_date: Optional[str] = Query(None, description="Filter records created after this date (ISO format: YYYY-MM-DD)"),
        to_date: Optional[str] = Query(None, description="Filter records created before this date (ISO format: YYYY-MM-DD)"),
        limit: Optional[int] = Query(None, description="Limit number of results"),
        offset: Optional[int] = Query(0, description="Offset for pagination")
):
    """
    Retrieve KYC status records with optional filtering.

    Query Parameters:
        - final_decision: Filter by status (PROCESSED/INPROCESS/FAILED)
        - customer_name: Search by customer name (partial match, case-insensitive)
        - identification_no: Exact match on identification number
        - from_date: Records created on or after this date
        - to_date: Records created on or before this date
        - limit: Maximum number of records to return
        - offset: Number of records to skip (for pagination)

    Returns:
        Filtered list of KYC status records
    """
    try:
        # Get file path from environment variable or use default
        status_file_path = os.getenv("KYC_STATUS_FILE", "data/kyc_status.json")

        # Convert to absolute path if relative
        if not Path(status_file_path).is_absolute():
            # Get project root (assuming api.py is in src/kyc_pipeline/)
            project_root = Path(__file__).parent.parent.parent
            status_file = project_root / status_file_path
        else:
            status_file = Path(status_file_path)

        # Check if file exists
        if not status_file.exists():
            raise HTTPException(
                status_code=404,
                detail=f"KYC status file not found at: {status_file}"
            )

        # Read and parse the JSON file
        with open(status_file, "r", encoding="utf-8") as f:
            kyc_data = json.load(f)

        # Apply filters
        filtered_data = kyc_data

        # Filter by final_decision
        if final_decision:
            final_decision_upper = final_decision.upper()
            filtered_data = [
                record for record in filtered_data
                if record.get("final_decision", "").upper() == final_decision_upper
            ]

        # Filter by customer_name (case-insensitive partial match)
        if customer_name:
            customer_name_lower = customer_name.lower()
            filtered_data = [
                record for record in filtered_data
                if customer_name_lower in record.get("customer_name", "").lower()
            ]

        # Filter by identification_no (exact match)
        if identification_no:
            filtered_data = [
                record for record in filtered_data
                if record.get("identification_no") == identification_no
            ]

        # Filter by date range
        if from_date:
            try:
                from_datetime = datetime.fromisoformat(from_date)
                filtered_data = [
                    record for record in filtered_data
                    if datetime.fromisoformat(record.get("created_at", "").replace("+08:00", "")) >= from_datetime
                ]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid from_date format. Use YYYY-MM-DD")

        if to_date:
            try:
                to_datetime = datetime.fromisoformat(to_date + "T23:59:59")
                filtered_data = [
                    record for record in filtered_data
                    if datetime.fromisoformat(record.get("created_at", "").replace("+08:00", "")) <= to_datetime
                ]
            except ValueError:
                raise HTTPException(status_code=400, detail="Invalid to_date format. Use YYYY-MM-DD")

        # Get total count before pagination
        total_filtered = len(filtered_data)

        # Apply pagination
        if offset:
            filtered_data = filtered_data[offset:]
        if limit:
            filtered_data = filtered_data[:limit]

        return {
            "total_records": len(kyc_data),
            "filtered_count": total_filtered,
            "returned_count": len(filtered_data),
            "offset": offset,
            "limit": limit,
            "data": filtered_data
        }

    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid JSON format in status file")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error reading status file: {str(e)}")