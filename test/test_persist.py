# tests/test_persist_tool.py
from __future__ import annotations

import json
from pathlib import Path
import importlib

import pytest

MODULE_PATH = "kyc_pipeline.tools.persist"


def _read_last_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        lines = [ln.strip() for ln in f if ln.strip()]
    assert lines, "Audit file should have at least one line"
    return json.loads(lines[-1])


def test_persist_writes_jsonl_and_returns_metadata(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """save_decision_record should append to JSONL and attempt SQLite insert."""
    mod = importlib.import_module(MODULE_PATH)
    tool = mod.save_decision_record

    audit_dir = tmp_path / "aud"
    db_path = tmp_path / "db" / "kyc_runs.db"

    monkeypatch.setenv("DECISIONS_AUDIT_DIR", str(audit_dir))
    monkeypatch.setenv("DECISIONS_DB_PATH", str(db_path))

    out = tool.run(
        "Approve",
        "All checks passed",
        "DOC-001",
        "Sarah Lee",
        "S1234567A",
    )
    meta = json.loads(out)

    # audit file exists and is append-only JSONL
    assert "audit_file" in meta
    audit_file = Path(meta["audit_file"])
    assert audit_file.exists()

    last = _read_last_jsonl(audit_file)
    assert last["final_decision"] == "Approve"
    assert last["explanation"] == "All checks passed"
    assert last["doc_id"] == "DOC-001"
    assert last["customer_name"] == "Sarah Lee"
    assert last["identification_no"] == "S1234567A"
    assert "created_at" in last and isinstance(last["created_at"], str)

    # DB row id is optional (None if DB write failed), but key should be present
    assert "db_row_id" in meta


def test_persist_appends_multiple_records(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    mod = importlib.import_module(MODULE_PATH)
    tool = mod.save_decision_record

    audit_dir = tmp_path / "aud2"
    db_path = tmp_path / "db2" / "runs.db"

    monkeypatch.setenv("DECISIONS_AUDIT_DIR", str(audit_dir))
    monkeypatch.setenv("DECISIONS_DB_PATH", str(db_path))

    # First write
    tool.run("Manual Review", "Address incomplete", "DOC-100", "A. Gomez", "G7654321Z")
    # Second write
    tool.run("Reject", "Watchlist match", "DOC-101", "John Patel", "P1111111B")

    audit_file = audit_dir / "decisions.jsonl"
    assert audit_file.exists()
    lines = [ln for ln in audit_file.read_text(encoding="utf-8").splitlines() if ln.strip()]
    assert len(lines) == 2

    first = json.loads(lines[0])
    second = json.loads(lines[1])
    assert first["final_decision"] == "Manual Review"
    assert second["final_decision"] == "Reject"