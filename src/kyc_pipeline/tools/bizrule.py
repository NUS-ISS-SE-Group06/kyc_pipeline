# -*- coding: utf-8 -*-
"""
Business rules validator (YAML-driven) for KYC payloads.

- Loads org policy from YAML (cached). Location is controlled by env KYC_RULES_DIR
  (fallback: <repo>/src/kyc_pipeline/config).
- Validates input JSON via a tight JSON Schema (reject unknown fields).
- Enforces YAML policy knobs including min/max age, name/id/address quality.
- "Validate-if-present": optional fields, when supplied, must still be valid.
- Exposes CrewAI tools:
    - fetch_business_rules(org_id)
    - evaluate_business_rules(org_id, extracted_json_string)

Default return:
{
  "violations": [{"code": "...", "text": "...", "citation": "..."}],
  "decision_hint": "APPROVE" | "REJECT"
}

If project defines RUNLOG_DIR and RUNLOG_FILE, the output will ALSO include:
  payload_json, out_dir, filename
so a strict runlog tool can accept this object when passed positionally.
"""
from __future__ import annotations

import json
import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from crewai.tools import tool
from jsonschema import ValidationError as SchemaError
from jsonschema import validate as json_validate

# ------------------------------ Constants ------------------------------------

_MAX_INCOMING_BYTES: int = 100_000  # guard against abnormally large payloads

# Cache for rules; keyed by org_id
_RULES_CACHE: Dict[str, Dict[str, Any]] = {}

# Default rules directory (…/src/kyc_pipeline/config)
_DEFAULT_RULES_DIR: Path = Path(__file__).resolve().parents[1] / "config"
_RULES_DIR: Path = Path(os.getenv("KYC_RULES_DIR", str(_DEFAULT_RULES_DIR))).resolve()


# ------------------------------ Helpers --------------------------------------

def _load_yaml_rules(org_id: str) -> Dict[str, Any]:
    """Load YAML policy for org (cached) and set sane defaults."""
    cached = _RULES_CACHE.get(org_id)
    path = _RULES_DIR / f"{org_id}.yaml"
    if cached and cached.get("_path") == str(path) and path.exists():
        return cached

    if not path.exists():
        raise FileNotFoundError(f"Rules file not found for org '{org_id}': {path}")

    with path.open("r", encoding="utf-8") as f:
        rules: Dict[str, Any] = yaml.safe_load(f) or {}

    # Defaults (policy knobs)
    rules.setdefault("min_age", 18)
    rules.setdefault("max_age", 120)  # 0/omit = disabled; 120 is a reasonable ceiling

    rules.setdefault("require_name", True)
    rules.setdefault("name_min_len", 2)
    rules.setdefault("name_max_len", 80)
    rules.setdefault("name_allow_regex", r"^[A-Za-z][A-Za-z\s\-\.'`]+$")

    rules.setdefault("require_dob", True)

    rules.setdefault("require_id_number", True)
    rules.setdefault("id_allow_regex", r"^[A-Za-z0-9-]+$")
    rules.setdefault("id_min_len", 8)    # 0 = disabled
    rules.setdefault("id_max_len", 12)   # 0 = disabled

    rules.setdefault("require_address", True)
    rules.setdefault("address_min_len", 10)
    rules.setdefault("address_min_words", 2)
    rules.setdefault("address_allow_regex", r"")  # empty = disable regex

    # keep for cache invalidation
    rules["_path"] = str(path)
    _RULES_CACHE[org_id] = rules
    return rules


@lru_cache(maxsize=1)
def _json_schema() -> Dict[str, Any]:
    """Return the static JSON schema (cached)."""
    return {
        "type": "object",
        "properties": {
            "name":      {"type": "string", "minLength": 1, "maxLength": 200},
            "dob":       {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"},
            "id_number": {"type": "string", "minLength": 1, "maxLength": 64},
            "address":   {"type": "string", "minLength": 1, "maxLength": 2000},
            "metadata":  {"type": "object"},  # optional bag for upstreams
        },
        "additionalProperties": False,
    }


def _parse_payload(extracted_json_string: Any) -> Dict[str, Any]:
    """Parse the input JSON into a dict; raise ValueError on invalid JSON."""
    if isinstance(extracted_json_string, dict):
        return extracted_json_string
    if isinstance(extracted_json_string, list):
        # normalize list to object so schema doesn't fail on top-level type
        return {"payload": extracted_json_string}
    if not isinstance(extracted_json_string, str):
        raise TypeError("extracted_json_string must be str|dict|list")
    try:
        obj = json.loads(extracted_json_string)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON payload: {exc}") from exc
    if not isinstance(obj, dict):
        raise ValueError("Top-level JSON must be an object")
    return obj


def _safe_regex(pattern: str) -> Optional[re.Pattern[str]]:
    """Compile pattern, returning None when pattern is empty/disabled."""
    patt = (pattern or "").strip()
    if not patt:
        return None
    return re.compile(patt)


def _calc_age(iso_date: str) -> Optional[int]:
    """Compute age in full years from YYYY-MM-DD; return None if invalid."""
    parts = iso_date.split("-")
    if len(parts) != 3:
        return None
    try:
        y, m, d = (int(parts[0]), int(parts[1]), int(parts[2]))
        dob = date(y, m, d)
    except (ValueError, TypeError):
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _count_words(text: str) -> int:
    """Count words (split on whitespace) in a string."""
    return len([w for w in re.split(r"\s+", (text or "").strip()) if w])


def _add(violations: List[Dict[str, str]], code: str, text: str, citation: Optional[str] = None) -> None:
    """Append a violation dict with optional policy citation."""
    violation: Dict[str, str] = {"code": code, "text": text}
    if citation:
        violation["citation"] = citation
    violations.append(violation)


# ------------------------------- Tools ---------------------------------------

@tool("fetch_business_rules")
def fetch_business_rules(org_id: str) -> str:
    """Return the merged policy for an org as JSON string."""
    rules = _load_yaml_rules(org_id).copy()
    rules.pop("_path", None)
    return json.dumps(rules, ensure_ascii=False, indent=2)


@tool("evaluate_business_rules")
def evaluate_business_rules(org_id: str, extracted_json_string: str) -> str:
    """
    Validate payload against:
      1) JSON Schema (reject unknown fields)
      2) YAML policy (min/max age, required-ness, quality checks, validate-if-present)

    Returns a JSON string with:
      {"violations":[...], "decision_hint":"APPROVE"|"REJECT"}

    If RUNLOG_DIR and RUNLOG_FILE are defined in the environment, the payload also
    includes payload_json/out_dir/filename so a strict runlog tool can accept this
    object when passed positionally.
    """
    # Size guard (defense-in-depth)
    if isinstance(extracted_json_string, str) and len(extracted_json_string.encode("utf-8")) > _MAX_INCOMING_BYTES:
        result = {
            "violations": [{"code": "PAYLOAD_TOO_LARGE", "text": "Payload exceeds limit", "citation": "size"}],
            "decision_hint": "REJECT",
        }
        return json.dumps(result, ensure_ascii=False, indent=2)

    rules = _load_yaml_rules(org_id)
    payload = _parse_payload(extracted_json_string)

    violations: List[Dict[str, str]] = []

    # 1) Schema validation (keep going after surfacing error so we add policy detail)
    try:
        json_validate(instance=payload, schema=_json_schema())
    except SchemaError as exc:
        _add(violations, "SCHEMA_INVALID", str(exc).splitlines()[0], "schema")

    # Extract fields (None if missing)
    name = payload.get("name")
    dob = payload.get("dob")
    idn = payload.get("id_number")
    addr = payload.get("address")

    # NAME (validate-if-present; require if require_name)
    if rules.get("require_name", True) and not name:
        _add(violations, "NAME_MISSING", "Name is required", "require_name")
    if name:
        nmin = int(rules.get("name_min_len", 2))
        nmax = int(rules.get("name_max_len", 80))
        if len(name) < nmin:
            _add(violations, "NAME_TOO_SHORT", f"Name shorter than {nmin}", "name_min_len")
        if len(name) > nmax:
            _add(violations, "NAME_TOO_LONG", f"Name longer than {nmax}", "name_max_len")
        rx_name = _safe_regex(rules.get("name_allow_regex", ""))
        if rx_name and not rx_name.match(name):
            _add(violations, "NAME_INVALID_CHARS", "Invalid characters in name", "name_allow_regex")

    # DOB / AGE
    if rules.get("require_dob", True) and not dob:
        _add(violations, "DOB_MISSING", "DOB is required (YYYY-MM-DD)", "require_dob")
    if dob:
        age = _calc_age(dob)
        if age is None:
            _add(violations, "DOB_INVALID", "DOB must be a real date in YYYY-MM-DD", "require_dob")
        else:
            amin = int(rules.get("min_age", 18))
            amax = int(rules.get("max_age", 120))
            if age < amin:
                _add(violations, "AGE_TOO_LOW", f"Age {age} < min {amin}", "min_age")
            if amax and age > amax:
                _add(violations, "AGE_TOO_HIGH", f"Age {age} > max {amax}", "max_age")

    # ID NUMBER
    if rules.get("require_id_number", True) and not idn:
        _add(violations, "ID_MISSING", "ID number is required", "require_id_number")
    if idn:
        imin = int(rules.get("id_min_len", 8))
        imax = int(rules.get("id_max_len", 12))
        if imin and len(idn) < imin:
            _add(violations, "ID_TOO_SHORT", f"ID shorter than {imin}", "id_min_len")
        if imax and len(idn) > imax:
            _add(violations, "ID_TOO_LONG", f"ID longer than {imax}", "id_max_len")
        rx_id = _safe_regex(rules.get("id_allow_regex", ""))
        if rx_id and not rx_id.fullmatch(idn):
            _add(violations, "ID_INVALID_CHARS", "Invalid characters/format in ID", "id_allow_regex")

    # ADDRESS
    if rules.get("require_address", True) and not addr:
        _add(violations, "ADDR_MISSING", "Address is required", "require_address")
    if addr:
        amin = int(rules.get("address_min_len", 10))
        wmin = int(rules.get("address_min_words", 2))
        if amin and len(addr) < amin:
            _add(violations, "ADDR_TOO_SHORT", f"Address shorter than {amin} characters", "address_min_len")
        if wmin and _count_words(addr) < wmin:
            _add(violations, "ADDR_TOO_FEW_WORDS", f"Address has fewer than {wmin} words", "address_min_words")
        rx_addr = _safe_regex(rules.get("address_allow_regex", ""))
        if rx_addr and not rx_addr.fullmatch(addr):
            _add(violations, "ADDR_INVALID_CHARS", "Invalid characters in address", "address_allow_regex")

    # Decision
    result: Dict[str, Any] = {
        "violations": violations,
        "decision_hint": ("REJECT" if violations else "APPROVE"),
    }

    # If the project already defines a log dir/file, include runlog-friendly keys
    # so a strict runlog tool can accept this object when passed positionally.
    out_dir = os.getenv("RUNLOG_DIR")
    filename = os.getenv("RUNLOG_FILE")
    if out_dir and filename:
        result_with_envelope = dict(result)
        result_with_envelope["payload_json"] = result
        result_with_envelope["out_dir"] = out_dir
        result_with_envelope["filename"] = filename
        return json.dumps(result_with_envelope, ensure_ascii=False, indent=2)

    # Otherwise, return the plain result (original behavior)
    return json.dumps(result, ensure_ascii=False, indent=2)
