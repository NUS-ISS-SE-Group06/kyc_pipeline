# tests/test_bizrule.py
# -*- coding: utf-8 -*-
"""Unit tests for kyc_pipeline.tools.bizrules (tool: fetch_business_rules).

The tests create temporary YAML policy files under the runtime config folder
that bizrules reads, then reload the module so its in-memory cache picks up the
new policy. Assertions are crisp and stable for Sonar compliance.
"""

from __future__ import annotations

import importlib
import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterator

# Project assumes PYTHONPATH=./src for imports.
import kyc_pipeline.tools.bizrules as bizrule


# ----------------------------- constants & helpers ----------------------------

CONFIG_DIR = Path(bizrule.__file__).resolve().parents[1] / "config"

VALID_NAME = "Jane Tan"
VALID_DOB = "1992-04-15"
VALID_ID = "A1234567B"
VALID_ADDR = "123 Orchard Road, Singapore"
VALID_EMAIL = "jane.tan@example.com"


def _write_text(path: Path, text: str) -> None:
    """Write UTF-8 text to a file, creating parent folders if needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _call_tool(fn: Any, *args: Any, **kwargs: Any) -> str:
    """Support both crewai tools (with .run) and plain callables."""
    return fn.run(*args, **kwargs) if hasattr(fn, "run") else fn(*args, **kwargs)


def _eval(payload: Dict[str, Any], org: str) -> Dict[str, Any]:
    """Call the tool and normalize its output to a dict (unwrap envelope if any)."""
    raw = _call_tool(bizrule.fetch_business_rules, org, json.dumps(payload))
    data = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(data, dict) and "payload_json" in data:
        return data["payload_json"]
    return data


def _reload_policies(org: str, yaml_lines: list[str]) -> Path:
    """Write a temp policy YAML and reload the module cache (force mtime bump)."""
    org_file = CONFIG_DIR / f"{org}.yaml"
    _write_text(org_file, "\n".join(yaml_lines) + "\n")
    now = time.time()
    os.utime(org_file, (now + 5, now + 5))
    importlib.reload(bizrule)
    return org_file


@contextmanager
def _temp_hide(path: Path) -> Iterator[None]:
    """Temporarily hide a file by renaming it; restore afterwards."""
    backup = path.with_suffix(path.suffix + ".bak")
    try:
        if path.exists():
            path.rename(backup)
        yield
    finally:
        if backup.exists():
            backup.rename(path)


# ------------------------------ core guarantees -------------------------------

def test_policy_missing_is_failsafe_rejects() -> None:
    """If no policy is available for org nor default, tool must REJECT with a POLICY_* code."""
    org = "does-not-exist"
    org_file = CONFIG_DIR / f"{org}.yaml"
    default_file = CONFIG_DIR / "non-sg-default.yaml"
    # Ensure org-specific does not exist
    if org_file.exists():
        org_file.unlink()
    # Temporarily hide default so nothing can load
    with _temp_hide(default_file):
        importlib.reload(bizrule)
        res = _eval({"name": "A", "dob": "2000-01-01", "id_number": "X1234567Z", "address": "101 Main St"}, org)
        assert res.get("decision_hint") == "REJECT"
        codes = {v.get("code") for v in res.get("violations", [])}
        assert any(c.startswith("POLICY_") for c in codes)


def test_hot_reload_without_sleep() -> None:
    """Changing YAML and bumping mtime should be picked up without process restart."""
    org = "acme-reload"
    org_file = _reload_policies(org, ["require_name: true", "name_min_len: 4"])
    res1 = _eval({"name": "Bob", "dob": "2000-01-01", "id_number": "A1234567B", "address": "101 Main St"}, org)
    assert any(v.get("code") == "NAME_TOO_SHORT" for v in res1.get("violations", []))

    # Soften policy
    org_file = _reload_policies(org, ["require_name: true", "name_min_len: 2"])
    res2 = _eval({"name": "Bob", "dob": "2000-01-01", "id_number": "A1234567B", "address": "101 Main St"}, org)
    assert not any(v.get("code") == "NAME_TOO_SHORT" for v in res2.get("violations", []))

    org_file.unlink(missing_ok=True)


def test_dynamic_constraints_only_if_declared() -> None:
    """Only declared keys in YAML are constrained; others aren’t validated unless required."""
    org = "policy-minimal"
    org_file = _reload_policies(org, ["require_id_number: true", "id_min_len: 8"])
    res = _eval({"name": "A", "dob": "1900-01-01", "id_number": "XYZ12345", "address": "A st"}, org)
    codes = {v.get("code") for v in res.get("violations", [])}
    assert "ID_TOO_SHORT" not in codes  # len 8 OK (XYZ12345)
    # No name/age constraints were declared; ensure not triggered spuriously
    assert "NAME_TOO_SHORT" not in codes
    assert "AGE_TOO_LOW" not in codes
    org_file.unlink(missing_ok=True)


# ------------------------------- scenarios A–M --------------------------------

def test_A_valid_payload_approves() -> None:
    org = "policy-approve"
    org_file = _reload_policies(
        org,
        [
            "require_name: true",
            "name_min_len: 2",
            "require_dob: true",
            "min_age: 18",
            "require_id_number: true",
            "id_min_len: 6",
            "require_address: true",
            "address_min_len: 8",
        ],
    )
    res = _eval({"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert res.get("decision_hint") == "APPROVE"
    assert res.get("violations") == []
    org_file.unlink(missing_ok=True)

def test_B_missing_address_rejects() -> None:
    org = "policy-missing-addr"
    org_file = CONFIG_DIR / f"{org}.yaml"
    _write_text(org_file, "require_address: true\naddress_min_len: 8\n")
    importlib.reload(bizrule)
    res = _eval({"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID}, org)
    assert res["decision_hint"] == "REJECT"
    assert any(v["code"] == "ADDR_MISSING" for v in res["violations"])
    if org_file.exists():
        org_file.unlink()

def test_C_schema_invalid_unknown_field() -> None:
    org = "policy-schema"
    org_file = _reload_policies(org, ["require_name: true", "require_dob: true", "require_id_number: true", "require_address: true"])
    res = _eval({"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR, "#unknown": "x"}, org)
    assert res.get("decision_hint") == "REJECT"
    assert any(v.get("code") == "SCHEMA_INVALID" for v in res.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_D_dob_format_invalid() -> None:
    org = "policy-dob-format"
    org_file = _reload_policies(org, ["require_dob: true"])
    res = _eval({"name": VALID_NAME, "dob": "15/04/1992", "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert any(v.get("code") == "DOB_INVALID" for v in res.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_E_age_below_minimum() -> None:
    org = "policy-age-min"
    org_file = _reload_policies(org, ["require_dob: true", "min_age: 30"])
    res = _eval({"name": VALID_NAME, "dob": "2015-01-01", "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert any(v.get("code") == "AGE_TOO_LOW" for v in res.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_F_age_above_maximum() -> None:
    org = "policy-age-max"
    org_file = _reload_policies(org, ["require_dob: true", "max_age: 40"])
    res = _eval({"name": VALID_NAME, "dob": "1950-01-01", "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert any(v.get("code") == "AGE_TOO_HIGH" for v in res.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_G_name_too_short() -> None:
    org = "policy-name-short"
    org_file = _reload_policies(org, ["name_min_len: 2"])
    res = _eval({"name": "J", "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert any(v.get("code") == "NAME_TOO_SHORT" for v in res.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_H_name_invalid_chars() -> None:
    org = "policy-name-regex"
    org_file = _reload_policies(org, ['name_allow_regex: "^[A-Za-z .\'-]+$"'])
    res = _eval({"name": "Jane$Tan", "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert any(v.get("code") == "NAME_INVALID_CHARS" for v in res.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_I_id_len_and_regex() -> None:
    org = "policy-idlen"
    org_file = _reload_policies(org, ["require_id_number: true", "id_min_len: 8", "id_max_len: 12", "id_allow_regex: '^[A-Z0-9]+$'"])

    def _run(val: str) -> Dict[str, Any]:
        return _eval({"name": "A B", "dob": "1990-01-01", "id_number": val, "address": "123 Main St"}, org)

    assert any(v.get("code") == "ID_TOO_SHORT" for v in _run("A12").get("violations", []))
    assert any(v.get("code") == "ID_TOO_LONG" for v in _run("A1234567890123").get("violations", []))
    assert any(v.get("code") == "ID_INVALID_CHARS" for v in _run("A123-4567B").get("violations", []))
    org_file.unlink(missing_ok=True)


def test_J_address_quality_short_and_words() -> None:
    org = "policy-addr"
    org_file = CONFIG_DIR / f"{org}.yaml"
    _write_text(org_file, "require_address: true\naddress_min_len: 8\naddress_min_words: 2\naddress_allow_regex: ''\n")
    importlib.reload(bizrule)
    r1 = _eval({"name": "A B", "dob": "1990-01-01", "id_number": VALID_ID, "address": "Blk 5"}, org)
    assert any(v["code"] == "ADDR_TOO_SHORT" for v in r1["violations"])
    r2 = _eval({"name": "A B", "dob": "1990-01-01", "id_number": VALID_ID, "address": "Unknownxxxxxxxx"}, org)
    assert any(v["code"] == "ADDR_TOO_FEW_WORDS" for v in r2["violations"])
    if org_file.exists():
        org_file.unlink()

def test_K1_optional_field_omitted_is_ok() -> None:
    org = "policy-optional-name"
    org_file = _reload_policies(org, ["require_dob: true", "min_age: 18", "require_id_number: true", "id_min_len: 6", "require_address: true", "address_min_len: 8"])
    res = _eval({"dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert not any(v.get("code", "").startswith("NAME_") for v in res.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_K2_optional_field_present_but_nonconforming_violates() -> None:
    org = "policy-optional-name2"
    org_file = _reload_policies(org, ["name_min_len: 2"])
    res = _eval({"name": "J", "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert any(v.get("code") == "NAME_TOO_SHORT" for v in res.get("violations", []))
    org_file.unlink(missing_ok=True)


# ------------------------------- scenarios N–Q --------------------------------

def test_N_email_required_and_regex() -> None:
    """Email is required and must match regex; good format clears EMAIL_*."""
    org = "policy-email"
    org_file = _reload_policies(
        org,
        [
            "require_name: true",
            "name_min_len: 2",
            "require_dob: true",
            "min_age: 18",
            "require_id_number: true",
            "id_min_len: 6",
            "require_address: true",
            "address_min_len: 8",
            "require_email: true",
            r"email_allow_regex: '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'",
        ],
    )

    r_missing = _eval({"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert any(v.get("code") == "EMAIL_MISSING" for v in r_missing.get("violations", []))

    r_bad = _eval({"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR, "email": "not-an-email"}, org)
    assert any(v.get("code") == "EMAIL_INVALID" for v in r_bad.get("violations", []))

    r_ok = _eval({"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR, "email": VALID_EMAIL}, org)
    assert not any(v.get("code", "").startswith("EMAIL_") for v in r_ok.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_O_face_photo_required_true() -> None:
    """When require_has_face_photo is true, has_face_photo must be True."""
    org = "policy-face"
    org_file = _reload_policies(
        org,
        [
            "require_name: true",
            "name_min_len: 2",
            "require_dob: true",
            "min_age: 18",
            "require_id_number: true",
            "id_min_len: 6",
            "require_address: true",
            "address_min_len: 8",
            "require_has_face_photo: true",
        ],
    )

    r_fail = _eval({"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR, "has_face_photo": False}, org)
    assert any(v.get("code") == "FACE_PHOTO_REQUIRED" for v in r_fail.get("violations", []))

    r_ok = _eval({"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR, "has_face_photo": True}, org)
    assert not any(v.get("code") == "FACE_PHOTO_REQUIRED" for v in r_ok.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_P_metadata_ignored_confidence_and_coverage_notes() -> None:
    """Confidence and coverage_notes are ignored; decision should APPROVE."""
    org = "policy-approve-meta"
    # Intentionally DO NOT declare has_face_photo here; we omit it from payload too.
    org_file = _reload_policies(
        org,
        [
            "require_name: true",
            "name_min_len: 2",
            "require_dob: true",
            "min_age: 18",
            "require_id_number: true",
            "id_min_len: 6",
            "require_address: true",
            "address_min_len: 8",
            "require_email: true",
            r"email_allow_regex: '^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$'",
        ],
    )

    res = _eval(
        {
            "name": VALID_NAME,
            "dob": VALID_DOB,
            "id_number": VALID_ID,
            "address": VALID_ADDR,
            "email": VALID_EMAIL,  # required by the YAML above
            # metadata that must be silently ignored:
            "confidence": 0.42,
            "coverage_notes": "Non-Singaporean KYC Sample Form",
        },
        org,
    )
    assert res.get("decision_hint") == "APPROVE"
    assert not any(v.get("code") == "SCHEMA_INVALID" for v in res.get("violations", []))
    org_file.unlink(missing_ok=True)


def test_Q_other_unknown_fields_are_flagged() -> None:
    """Unknown non-metadata fields should cause SCHEMA_INVALID and REJECT."""
    org = "policy-unknowns"
    org_file = _reload_policies(
        org,
        [
            "require_name: true",
            "name_min_len: 2",
            "require_dob: true",
            "min_age: 18",
            "require_id_number: true",
            "id_min_len: 6",
            "require_address: true",
            "address_min_len: 8",
        ],
    )

    res = _eval(
        {"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR, "weight": 48, "height": 160},
        org,
    )
    assert any(v.get("code") == "SCHEMA_INVALID" for v in res.get("violations", []))
    assert res.get("decision_hint") == "REJECT"
    org_file.unlink(missing_ok=True)
