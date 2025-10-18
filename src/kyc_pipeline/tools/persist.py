
# src/kyc_pipeline/tools/persist.py
import json, tempfile, os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional, List, Union
from crewai.tools import tool

# ---------- helpers ----------

def _utc_now_iso() -> str:
    """ISO 8601 timestamp with timezone, second precision."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _ensure_db_schema(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS kyc_decisions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at        TEXT NOT NULL,          -- time row was created (UTC)
                modified_at       TEXT,                   -- optional explicit modified_at
                doc_id            TEXT,
                file_name         TEXT,
                customer_name     TEXT,
                identification_no TEXT,
                email_id          TEXT,
                final_decision    TEXT NOT NULL,
                explanation       TEXT NOT NULL,
                audit_log         TEXT                    -- JSON-encoded list of strings
            )
            """
        )
        conn.commit()


def _insert_db_record(
    db_path: Path,
    *,
    created_at: str,
    modified_at: Optional[str],
    doc_id: Optional[str],
    file_name: Optional[str],
    customer_name: Optional[str],
    identification_no: Optional[str],
    email_id: Optional[str],
    final_decision: str,
    explanation: str,
    audit_log_json: Optional[str],
) -> int:
    _ensure_db_schema(db_path)
    with sqlite3.connect(db_path) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO kyc_decisions
              (created_at, modified_at, doc_id, file_name, customer_name,
               identification_no, email_id, final_decision, explanation, audit_log)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                created_at,
                modified_at,
                doc_id,
                file_name,
                customer_name,
                identification_no,
                email_id,
                final_decision,
                explanation,
                audit_log_json,
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def _append_jsonl_in_dir(out_dir: Path, payload: dict) -> Path:
    """Append as JSONL into <out_dir>/decisions.jsonl (ensure dir exists)."""
    out_dir.mkdir(parents=True, exist_ok=True)
    fpath = out_dir / "decisions.jsonl"
    with fpath.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return fpath


def _append_jsonl_to_file(file_path: Path, payload: dict) -> Path:
    """Append as JSONL into an explicit file path (ensure parent dir exists)."""
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with file_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    return file_path


# ---------- tool ----------

@tool("save_decision_record")
def save_decision_record(
    # all optional & tolerant; agent can pass any subset
    final_decision: Optional[str] = None,
    explanation: Optional[str] = None,
    doc_id: Optional[str] = None,
    file_name: Optional[str] = None,
    customer_name: Optional[str] = None,
    identification_no: Optional[str] = None,
    email_id: Optional[str] = None,
    created_at: Optional[str] = None,
    modified_at: Optional[str] = None,
    audit_log: Optional[Union[List[str], str]] = None,
    **kwargs,
) -> str:
    """
    Persist the final KYC decision (DB + JSONL audit).
    Tolerant to arg-name variants commonly produced by LLMs.

    Known aliases handled:
      - final_decision: 'decision', 'finalDecision', 'verdict', 'status'
      - explanation: 'reason', 'rationale', 'explain', 'message'
      - doc_id: 'docId', 'document_id', 'documentId'
      - file_name: 'File_Name', 'fileName', 'filename'
      - customer_name: 'name', 'customerName', 'applicant'
      - identification_no: 'id_number', 'idNumber', 'national_id', 'nric', 'passport'
      - email_id: 'email', 'to', 'email_to', 'recipient'
      - created_at/modified_at: timestamps (ISO preferred); if missing, we fill defaults
      - audit_log: either list[str] or single string; we normalize to list[str]
    """

    # ---------- alias normalization ----------
    if final_decision is None:
        final_decision = (
            kwargs.get("decision")
            or kwargs.get("finalDecision")
            or kwargs.get("verdict")
            or kwargs.get("status")
        )
    if explanation is None:
        explanation = (
            kwargs.get("explanation")
            or kwargs.get("reason")
            or kwargs.get("rationale")
            or kwargs.get("explain")
            or kwargs.get("message")
        )
    if doc_id is None:
        doc_id = kwargs.get("docId") or kwargs.get("document_id") or kwargs.get("documentId")
    if file_name is None:
        file_name = kwargs.get("File_Name") or kwargs.get("fileName") or kwargs.get("filename")
    if customer_name is None:
        customer_name = kwargs.get("name") or kwargs.get("customerName") or kwargs.get("applicant")
    if identification_no is None:
        identification_no = (
            kwargs.get("id_number")
            or kwargs.get("idNumber")
            or kwargs.get("national_id")
            or kwargs.get("nric")
            or kwargs.get("passport")
        )
    if email_id is None:
        email_id = kwargs.get("email_id") or kwargs.get("email") or kwargs.get("to") or kwargs.get("email_to") or kwargs.get("recipient")
    if created_at is None:
        created_at = kwargs.get("createdAt") or kwargs.get("created_at")
    if modified_at is None:
        modified_at = kwargs.get("modifiedAt") or kwargs.get("modified_at")
    if audit_log is None:
        audit_log = kwargs.get("audit") or kwargs.get("auditTrail") or kwargs.get("audit_log")

    # ---------- guardrails / defaults ----------
    final_decision = (final_decision or "UNKNOWN").upper()
    explanation = explanation or "No explanation provided."

    created_at = created_at or _utc_now_iso()
    # If modified_at not provided, mirror created_at (keeps both populated for reviewers)
    modified_at = modified_at or created_at

    # normalize audit_log to a list[str]
    if isinstance(audit_log, str):
        audit_log_list: List[str] = [audit_log]
    elif isinstance(audit_log, list):
        audit_log_list = [str(x) for x in audit_log]
    else:
        audit_log_list = []

    # ---------- persist ----------
    db_path = Path(os.getenv("DECISIONS_DB_PATH", "kyc_local.db"))

    # DB insert (never crash if DB write fails)
    row_id: Optional[int] = None
    try:
        row_id = _insert_db_record(
            db_path=db_path,
            created_at=created_at,
            modified_at=modified_at,
            doc_id=doc_id,
            file_name=file_name,
            customer_name=customer_name,
            identification_no=identification_no,
            email_id=email_id,
            final_decision=final_decision,
            explanation=explanation,
            audit_log_json=json.dumps(audit_log_list, ensure_ascii=False),
        )
    except Exception:
        row_id = None

    # JSONL audit append (supports either single-file or directory mode)
    audit_payload = {
        "created_at": created_at,
        "modified_at": modified_at,
        "doc_id": doc_id,
        "file_name": file_name,
        "customer_name": customer_name,
        "identification_no": identification_no,
        "email_id": email_id,
        "final_decision": final_decision,
        "explanation": explanation,
        "audit_log": audit_log_list,
    }

    # AFTER (always JSONL when KYC_STATUS_FILE is set)
    kyc_status_file = os.getenv("KYC_STATUS_FILE")
    if kyc_status_file:
        fpath = Path(kyc_status_file)
        audit_file = _append_jsonl_to_file(fpath, audit_payload)
    else:
        audit_dir = Path(os.getenv("DECISIONS_AUDIT_DIR", "runlogs"))
        audit_file = _append_jsonl_in_dir(audit_dir, audit_payload)

    return json.dumps(
        {
            "db_row_id": row_id,
            "audit_file": str(audit_file),
        },
        ensure_ascii=False,
    )

# ensure pydantic model is fully built for some CrewAI wrappers
save_decision_record.model_rebuild()

def _atomic_write_text(dest: Path, text: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=str(dest.parent), delete=False) as tmp:
        tmp.write(text)
        tmp.flush()
        os.fsync(tmp.fileno())
        tmp_path = Path(tmp.name)
    tmp_path.replace(dest)

def _append_to_json_array_file(file_path: Path, payload: Dict[str, Any]) -> Path:
    """
    Append (or repair then append) to a JSON **array file** safely and atomically.
    If the file is missing, creates: [<payload>].
    If the file was corrupted by JSONL appends, it salvages the array and
    pulls valid trailing objects into the array.
    """
    arr: List[Dict[str, Any]] = []
    if file_path.exists():
        raw = file_path.read_text(encoding="utf-8").strip()
        # Fast path: valid array
        try:
            maybe = json.loads(raw)
            if isinstance(maybe, list):
                arr = maybe
            elif isinstance(maybe, dict):
                arr = [maybe]
        except Exception:
            # Repair path: look for last closing bracket of an array
            end_idx = raw.rfind("]")
            if end_idx != -1:
                head = raw[: end_idx + 1]
                tail = raw[end_idx + 1 :].strip()
                try:
                    base = json.loads(head)
                    if isinstance(base, list):
                        arr = base
                except Exception:
                    arr = []
                # Try to parse any trailing JSONL-ish objects
                for line in tail.splitlines():
                    line = line.strip().rstrip(",")
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                        if isinstance(obj, dict):
                            arr.append(obj)
                    except Exception:
                        # ignore junk
                        pass
            else:
                # could not repair, start fresh
                arr = []
    # Append the new record and write atomically
    arr.append(payload)
    _atomic_write_text(file_path, json.dumps(arr, ensure_ascii=False, indent=2))
    return file_path