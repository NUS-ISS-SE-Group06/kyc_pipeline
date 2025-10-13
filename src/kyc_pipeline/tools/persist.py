# src/kyc_pipeline/tools/persist.py
from __future__ import annotations

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional
from crewai.tools import tool


def _ensure_db_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at TEXT NOT NULL,
                doc_id TEXT,
                customer_name TEXT,
                identification_no TEXT,
                final_decision TEXT NOT NULL,
                explanation TEXT NOT NULL
            )
            """
        )
        conn.commit()


def _insert_db_record(
    db_path: Path,
    final_decision: str,
    explanation: str,
    doc_id: Optional[str],
    customer_name: Optional[str],
    identification_no: Optional[str],
) -> int:
    _ensure_db_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO decisions
              (created_at, doc_id, customer_name, identification_no, final_decision, explanation)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.utcnow().isoformat(timespec="seconds"),
                doc_id,
                customer_name,
                identification_no,
                final_decision,
                explanation,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _append_jsonl_audit(
    out_dir: Path,
    payload: dict,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    fpath = out_dir / "decisions.jsonl"
    with fpath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return fpath


@tool("save_decision_record")
def save_decision_record(
    final_decision: str,
    explanation: str,
    doc_id: Optional[str] = None,
    customer_name: Optional[str] = None,
    identification_no: Optional[str] = None,
) -> str:
    """
    Persist the final KYC decision.

    - Writes a row into SQLite (file `kyc_runs.db`, overridable via DECISIONS_DB_PATH).
    - Appends a JSONL line into runlogs/decisions.jsonl (overridable via DECISIONS_AUDIT_DIR).
    Returns a short JSON string: {"db_row_id": <int|null>, "audit_file": "<path>"}
    """
    # DB
    db_path = Path(os.getenv("DECISIONS_DB_PATH", "kyc_runs.db"))
    row_id: Optional[int] = None
    try:
        row_id = _insert_db_record(
            db_path=db_path,
            final_decision=final_decision,
            explanation=explanation,
            doc_id=doc_id,
            customer_name=customer_name,
            identification_no=identification_no,
        )
    except Exception:
        # Don’t crash tool on DB write issues; still do file audit
        row_id = None

    # JSONL audit file
    audit_payload = {
        "created_at": datetime.utcnow().isoformat(timespec="seconds"),
        "doc_id": doc_id,
        "customer_name": customer_name,
        "identification_no": identification_no,
        "final_decision": final_decision,
        "explanation": explanation,
    }
    audit_dir = Path(os.getenv("DECISIONS_AUDIT_DIR", "runlogs"))
    audit_file = _append_jsonl_audit(audit_dir, audit_payload)

    return json.dumps({"db_row_id": row_id, "audit_file": str(audit_file)})