# -*- coding: utf-8 -*-
"""Unit tests for kyc_pipeline.tools.bizrule with validate-if-present behavior."""
from __future__ import annotations

import json
from typing import Any

import pytest
import kyc_pipeline.tools.bizrule as bizrule  # import the module that defines @tool

# Reusable constants to avoid “magic values”
ORG_ID = "non-sg-default"
VALID_NAME = "Jane Tan"
VALID_DOB = "1992-04-15"
VALID_ID = "A1234567B"
VALID_ADDR = "123 Orchard Rd, #05-01"


def _call_tool(fn: Any, *args: Any, **kwargs: Any) -> Any:
    """Call plain functions or CrewAI tools uniformly."""
    # CrewAI tools expose .run(...)
    if hasattr(fn, "run"):
        return fn.run(*args, **kwargs)
    return fn(*args, **kwargs)


@pytest.fixture(scope="module")
def rules() -> dict[str, Any]:
    """Fetch rules once for shape checks."""
    raw = _call_tool(bizrule.fetch_business_rules, ORG_ID)
    return json.loads(raw) if isinstance(raw, str) else raw


def _eval(payload: dict[str, Any], org_id: str = ORG_ID) -> dict[str, Any]:
    """Evaluate a payload through the tool and return parsed JSON."""
    raw = _call_tool(bizrule.evaluate_business_rules, org_id, json.dumps(payload))
    return json.loads(raw) if isinstance(raw, str) else raw


# ------------------------------- Tests ---------------------------------------

def test_rules_shape(rules: dict[str, Any]) -> None:
    """Rules include all policy knobs with correct types."""
    for key in (
        "min_age", "max_age",
        "require_name", "name_min_len", "name_max_len", "name_allow_regex",
        "require_dob",
        "require_id_number", "id_allow_regex", "id_min_len", "id_max_len",
        "require_address", "address_min_len", "address_min_words", "address_allow_regex",
    ):
        assert key in rules, f"Missing key in rules: {key}"
    assert isinstance(rules["min_age"], int)


def test_pass_valid_payload() -> None:
    """Valid payload should approve with no violations."""
    payload = {"name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR}
    res = _eval(payload)
    assert res["decision_hint"] == "APPROVE"
    assert res["violations"] == []


def test_fail_policy_underage_and_missing_address() -> None:
    """Underage + short name + missing address -> reject with expected codes."""
    payload = {"name": "A", "dob": "2010-01-01", "id_number": "Z7654321X"}  # address missing
    res = _eval(payload)
    codes = {v["code"] for v in res["violations"]}
    assert res["decision_hint"] == "REJECT"
    assert {"AGE_TOO_LOW", "ADDR_MISSING", "NAME_TOO_SHORT"} <= codes


def test_fail_schema_unknown_field() -> None:
    """Unknown top-level field should trigger schema violation."""
    payload = {
        "name": VALID_NAME, "dob": VALID_DOB, "id_number": VALID_ID, "address": VALID_ADDR,
        "smoker": "YES",  # unknown
    }
    res = _eval(payload)
    assert res["decision_hint"] == "REJECT"
    assert any(v["code"] == "SCHEMA_INVALID" for v in res["violations"])


def test_dob_invalid_format_not_real_date() -> None:
    """Invalid date should be rejected."""
    payload = {"name": "Jane", "dob": "1990-13-40", "id_number": VALID_ID, "address": "123 Orchard"}
    res = _eval(payload)
    assert res["decision_hint"] == "REJECT"
    assert any(v["code"] == "DOB_INVALID" for v in res["violations"])


def test_name_regex_invalid_chars() -> None:
    """Name with invalid characters should be rejected."""
    payload = {"name": "J@ne", "dob": VALID_DOB, "id_number": VALID_ID, "address": "123 Orchard"}
    res = _eval(payload)
    assert res["decision_hint"] == "REJECT"
    assert any(v["code"] == "NAME_INVALID_CHARS" for v in res["violations"])


def test_name_length_policy() -> None:
    """Overly long name should be rejected."""
    payload = {"name": "A" * 100, "dob": VALID_DOB, "id_number": VALID_ID, "address": "123 Orchard"}
    res = _eval(payload)
    assert res["decision_hint"] == "REJECT"
    assert any(v["code"] == "NAME_TOO_LONG" for v in res["violations"])


def test_optional_fields_validate_if_present() -> None:
    """Optional fields, when provided, must still be valid."""
    payload = {
        "name": "Jane",
        "dob": VALID_DOB,
        "id_number": "$1234567A",        # invalid by regex
        "address": "Blk 5",               # too short, too few words
    }
    res = _eval(payload)
    codes = {v["code"] for v in res["violations"]}
    assert "ID_INVALID_CHARS" in codes
    assert "ADDR_TOO_SHORT" in codes
    assert res["decision_hint"] == "REJECT"


def test_id_length_knobs(tmp_path, monkeypatch) -> None:
    """Org with tighter ID length should enforce min/max and regex."""
    org = "policy-idlen"
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / f"{org}.yaml").write_text("\n".join([
        "require_id_number: true",
        "id_allow_regex: '^[A-Za-z0-9-]+$'",
        "id_min_len: 8",
        "id_max_len: 12",
    ]), encoding="utf-8")

    # Point bizrule to temp rules dir and clear cache
    monkeypatch.setenv("KYC_RULES_DIR", str(rules_dir))
    import kyc_pipeline.tools.bizrule as br  # re-import for patched path
    monkeypatch.setattr(br, "_RULES_DIR", rules_dir, raising=True)
    br._RULES_CACHE.clear()

    def eval_id(val: str) -> dict[str, Any]:
        payload = {"name": "A B", "dob": "1990-01-01", "id_number": val, "address": "123 Main St"}
        raw = _call_tool(br.evaluate_business_rules, org, json.dumps(payload))
        return json.loads(raw)

    assert any(v["code"] == "ID_TOO_SHORT" for v in eval_id("A123456")["violations"])          # 7
    assert any(v["code"] == "ID_TOO_LONG"  for v in eval_id("A1234567890123")["violations"])   # 13
    assert any(v["code"] == "ID_INVALID_CHARS" for v in eval_id("$1234567A")["violations"])
    assert eval_id("A1234567B")["decision_hint"] == "APPROVE"


def test_age_too_high_with_max_age(tmp_path, monkeypatch) -> None:
    """Max-age should be enforced when configured."""
    org = "policy-age"
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / f"{org}.yaml").write_text("min_age: 18\nmax_age: 120\n", encoding="utf-8")

    monkeypatch.setenv("KYC_RULES_DIR", str(rules_dir))
    import kyc_pipeline.tools.bizrule as br
    monkeypatch.setattr(br, "_RULES_DIR", rules_dir, raising=True)
    br._RULES_CACHE.clear()

    payload = {"name": "A B", "dob": "1890-01-01", "id_number": VALID_ID, "address": "123 Main"}
    raw = _call_tool(br.evaluate_business_rules, org, json.dumps(payload))
    res = json.loads(raw)
    assert any(v["code"] == "AGE_TOO_HIGH" for v in res["violations"])


def test_address_quality_with_regex_disabled(tmp_path, monkeypatch) -> None:
    """Address min length and word count should apply when regex is disabled."""
    org = "policy-addr"
    rules_dir = tmp_path / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    (rules_dir / f"{org}.yaml").write_text("\n".join([
        "require_address: true",
        "address_min_len: 10",
        "address_min_words: 2",
        "address_allow_regex: ''",
    ]), encoding="utf-8")

    monkeypatch.setenv("KYC_RULES_DIR", str(rules_dir))
    import kyc_pipeline.tools.bizrule as br
    monkeypatch.setattr(br, "_RULES_DIR", rules_dir, raising=True)
    br._RULES_CACHE.clear()

    r1 = _eval({"name": "A B", "dob": "1990-01-01", "id_number": VALID_ID, "address": "Blk 5"}, org)
    assert any(v["code"] == "ADDR_TOO_SHORT" for v in r1["violations"])

    r2 = _eval({"name": "A B", "dob": "1990-01-01", "id_number": VALID_ID, "address": "Unknownxxxxxxxx"}, org)
    assert any(v["code"] == "ADDR_TOO_FEW_WORDS" for v in r2["violations"])

    r3 = _eval({"name": "A B", "dob": "1990-01-01", "id_number": VALID_ID, "address": VALID_ADDR}, org)
    assert r3["decision_hint"] == "APPROVE"
