# tests/test_persist_tool.py
import json
import importlib
from pathlib import Path

import pytest

MODULE_PATH = "kyc_pipeline.tools.persist"


def _read_last_jsonl(path: Path) -> dict:
    """Read and parse the last non-empty JSONL line."""
    text = path.read_text(encoding="utf-8")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    assert lines, "Audit file should contain at least one line"
    return json.loads(lines[-1])


def test_persist_to_explicit_file_and_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    When KYC_STATUS_FILE is set to a file path, the tool should append JSONL to that file.
    Also set DECISIONS_DB_PATH to a tmp sqlite file so DB insert is attempted.
    """
    mod = importlib.import_module(MODULE_PATH)
    tool = mod.save_decision_record

    # Point to a temp JSONL file and temp DB
    kyc_status_file = tmp_path / "data" / "kyc_status.json"
    db_path = tmp_path / "db" / "kyc_local.db"
    monkeypatch.setenv("KYC_STATUS_FILE", str(kyc_status_file))
    monkeypatch.setenv("DECISIONS_DB_PATH", str(db_path))

    # Call the tool with positional args (decision, explanation, doc_id, file_name, customer_name, identification_no, email_id)
    out_json = tool.run(
        "Approve",
        "All checks passed",
        "DOC-001",
        "KYC_20250915_0001.pdf",
        "Sarah Lee",
        "S1234567A",
        "sarah.lee@example.com",
    )
    meta = json.loads(out_json)

    # audit file exists and is JSONL
    assert "audit_file" in meta
    audit_path = Path(meta["audit_file"])
    assert audit_path.exists()

    last = _read_last_jsonl(audit_path)
    # Persist tool upper-cases the decision
    assert last["final_decision"] == "APPROVE"
    assert last["explanation"] == "All checks passed"
    assert last["doc_id"] == "DOC-001"
    assert last["file_name"] == "KYC_20250915_0001.pdf"
    assert last["customer_name"] == "Sarah Lee"
    assert last["identification_no"] == "S1234567A"
    assert last["email_id"] == "sarah.lee@example.com"
    assert isinstance(last.get("audit_log"), list)
    # created_at / modified_at exist and look ISO-ish
    assert "T" in last["created_at"]
    assert "T" in last["modified_at"]

    # DB row id presence (may be None if db insert failed, but key must exist)
    assert "db_row_id" in meta


def test_persist_directory_fallback_and_multiple_appends(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    With no KYC_STATUS_FILE, tool should write to DECISIONS_AUDIT_DIR/decisions.jsonl.
    Appending twice should produce two lines.
    """
    mod = importlib.import_module(MODULE_PATH)
    tool = mod.save_decision_record

    audit_dir = tmp_path / "runlogs_here"
    db_path = tmp_path / "db2" / "kyc_local.db"
    monkeypatch.delenv("KYC_STATUS_FILE", raising=False)
    monkeypatch.setenv("DECISIONS_AUDIT_DIR", str(audit_dir))
    monkeypatch.setenv("DECISIONS_DB_PATH", str(db_path))

    # First append
    tool.run("Manual Review", "Address incomplete", "DOC-100", "docA.pdf", "A. Gomez", "G7654321Z", "a.gomez@example.com")
    # Second append
    tool.run("Reject", "Watchlist match", "DOC-101", "docB.pdf", "John Patel", "P1111111B", "john.patel@example.com")

    audit_file = audit_dir / "decisions.jsonl"
    assert audit_file.exists(), "decisions.jsonl should be created in the provided directory"

    lines = [ln for ln in audit_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2, "Two calls should append two lines"

    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["final_decision"] == "MANUAL REVIEW"
    assert second["final_decision"] == "REJECT"


def test_persist_alias_arguments_are_normalized(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """
    The tool should accept alias names (status, reason, document_id, File_Name, etc.)
    and normalize them into the persisted structure.
    """
    mod = importlib.import_module(MODULE_PATH)
    tool = mod.save_decision_record

    kyc_status_file = tmp_path / "logs" / "kyc.jsonl"
    db_path = tmp_path / "db3" / "sqlite.db"
    monkeypatch.setenv("KYC_STATUS_FILE", str(kyc_status_file))
    monkeypatch.setenv("DECISIONS_DB_PATH", str(db_path))

    # Use alias keyword args:
    out_json = tool.run(
        status="Processed",              # alias for final_decision
        reason="All checks OK",          # alias for explanation
        document_id="DOC-555",           # alias for doc_id
        File_Name="KYC_20250915_0005.pdf",  # alias for file_name
        name="Aarav Patel",              # alias for customer_name
        id_number="S8888888A",           # alias for identification_no
        email="aarav.patel@example.com", # alias for email_id
        audit=["step1 ok", "step2 ok"],  # accepted list[str]
    )
    meta = json.loads(out_json)
    audit_path = Path(meta["audit_file"])
    last = _read_last_jsonl(audit_path)

    # Decision is upper-cased by the tool
    assert last["final_decision"] == "PROCESSED"
    assert last["explanation"] == "All checks OK"
    assert last["doc_id"] == "DOC-555"
    assert last["file_name"] == "KYC_20250915_0005.pdf"
    assert last["customer_name"] == "Aarav Patel"
    assert last["identification_no"] == "S8888888A"
    assert last["email_id"] == "aarav.patel@example.com"
    assert last["audit_log"] == ["step1 ok", "step2 ok"]