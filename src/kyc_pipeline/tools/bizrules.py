# -*- coding: utf-8 -*-
"""
BizRules validator (YAML-driven) — single tool named 'fetch_business_rules'.

Guarantees
----------
1) Fail-safe if YAML is missing: returns POLICY_NOT_FOUND + REJECT (no hardcoded defaults).
2) Hot-reload on YAML file change via mtime (no restart).
3) Dynamic checks only when corresponding YAML keys exist.
4) JSON schema is ALWAYS enforced and is derived from YAML (no hardcoded thresholds).

Import (crew.py)
----------------
from kyc_pipeline.tools.bizrule import fetch_business_rules
"""

from __future__ import annotations

import json
import os
import re
from datetime import date
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from crewai.tools import tool
from jsonschema import ValidationError as SchemaError
from jsonschema import validate as json_validate


# ------------------------------ Constants & Cache -----------------------------

_MAX_INCOMING_BYTES: int = 100_000  # payload guardrail
_RULES_CACHE: Dict[str, Dict[str, Any]] = {}  # org_id -> {"rules": dict, "path": str, "mtime": float}

# Always use the repo config folder: <project_root>/kyc_pipeline/config
_DEFAULT_RULES_DIR: Path = Path(__file__).resolve().parents[1] / "config"
_RULES_DIR: Path = _DEFAULT_RULES_DIR


# ------------------------------ File Helpers ---------------------------------

def _file_mtime(path: Path) -> Optional[float]:
    """Return mtime for a file or None if not available."""
    try:
        return path.stat().st_mtime
    except OSError:
        return None


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    """Load YAML into a dict using safe loader; return None if file cannot be read."""
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except OSError:
        return None


def _load_yaml_rules(org_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[float]]:
    """
    Try <org_id>.yaml first, then non-sg-default.yaml.
    Returns (rules, source_path, mtime) or (None, None, None) if not found.
    """
    primary = _RULES_DIR / f"{org_id}.yaml"
    if primary.exists():
        return _load_yaml(primary), str(primary), _file_mtime(primary)

    fallback = _RULES_DIR / "non-sg-default.yaml"
    if fallback.exists():
        return _load_yaml(fallback), str(fallback), _file_mtime(fallback)

    return None, None, None


def _get_rules_hot(org_id: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Cached load with hot-reload on mtime change.
    Returns (rules, source_path) or (None, None) if not found anywhere.
    """
    cached = _RULES_CACHE.get(org_id)
    rules, src, mtime = _load_yaml_rules(org_id)

    if rules is None:
        return None, None

    if cached is None:
        _RULES_CACHE[org_id] = {"rules": rules, "path": src, "mtime": mtime}
        return rules, src

    if cached.get("path") == src:
        if cached.get("mtime") != mtime:
            _RULES_CACHE[org_id] = {"rules": rules, "path": src, "mtime": mtime}
        return _RULES_CACHE[org_id]["rules"], _RULES_CACHE[org_id]["path"]

    # Source switched (e.g., primary appeared after fallback)
    _RULES_CACHE[org_id] = {"rules": rules, "path": src, "mtime": mtime}
    return rules, src


# ------------------------------ Validation Helpers ---------------------------

def _safe_regex(pattern: Optional[str]) -> Optional[re.Pattern[str]]:
    """Compile a regex if pattern is truthy; otherwise return None."""
    patt = (pattern or "").strip()
    return re.compile(patt) if patt else None


def _calc_age(iso_date: str) -> Optional[int]:
    """Compute age in years for YYYY-MM-DD; return None if invalid."""
    parts = iso_date.split("-")
    if len(parts) != 3:
        return None
    try:
        year, month, day = (int(parts[0]), int(parts[1]), int(parts[2]))
        dob = date(year, month, day)
    except (ValueError, TypeError):
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _count_words(text: str) -> int:
    """Count space-separated words in a string."""
    return len([w for w in re.split(r"\s+", (text or "").strip()) if w])


def _add(violations: List[Dict[str, str]], code: str, msg: str, citation: Optional[str] = None) -> None:
    """Append a violation entry (machine-friendly code + human text)."""
    v: Dict[str, str] = {"code": code, "text": msg}
    if citation:
        v["citation"] = citation
    violations.append(v)


def _build_schema_from_rules(rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a JSON schema dynamically from YAML rules (no hardcoded thresholds).
    If a policy knob isn't present in YAML, the schema won't enforce it.
    """
    props: Dict[str, Any] = {}

    # name: constrain only if YAML provides knobs or requires name
    if any(k in rules for k in ("require_name", "name_min_len", "name_max_len", "name_allow_regex")):
        name_schema: Dict[str, Any] = {"type": "string"}
        nmin = rules.get("name_min_len")
        nmax = rules.get("name_max_len")
        if isinstance(nmin, int):
            name_schema["minLength"] = nmin
        if isinstance(nmax, int):
            name_schema["maxLength"] = nmax
        props["name"] = name_schema

    # dob: enforce date format only if DOB-related knobs exist
    if any(k in rules for k in ("require_dob", "min_age", "max_age")):
        props["dob"] = {"type": "string", "pattern": r"^\d{4}-\d{2}-\d{2}$"}

    # id_number: length constraints if present
    if any(k in rules for k in ("require_id_number", "id_min_len", "id_max_len", "id_allow_regex")):
        id_schema: Dict[str, Any] = {"type": "string"}
        imin = rules.get("id_min_len")
        imax = rules.get("id_max_len")
        if isinstance(imin, int):
            id_schema["minLength"] = imin
        if isinstance(imax, int):
            id_schema["maxLength"] = imax
        props["id_number"] = id_schema

    # address: type only (policy handles word/regex checks)
    if any(k in rules for k in ("require_address", "address_min_len", "address_min_words", "address_allow_regex")):
        props["address"] = {"type": "string"}

    # metadata: allowed as free-form object
    props["metadata"] = {"type": "object"}

    return {
        "type": "object",
        "properties": props,
        "additionalProperties": False,  # set True if you want to allow extra keys
    }


@lru_cache(maxsize=1)
def _base_schema() -> Dict[str, Any]:
    """
    A minimal base schema that ensures object shape when rules are absent.
    Used only if YAML has no relevant keys (rare).
    """
    return {"type": "object", "properties": {"metadata": {"type": "object"}}, "additionalProperties": False}


def _parse_payload(extracted_json_string: Any) -> Dict[str, Any]:
    """Parse JSON string or pass through dict/list; raise for invalid types."""
    if isinstance(extracted_json_string, dict):
        return extracted_json_string
    if isinstance(extracted_json_string, list):
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


# ------------------------------ Single Tool ----------------------------------

@tool("fetch_business_rules")
def fetch_business_rules(org_id: str, extracted_json_string: str) -> str:
    """
    Single tool that EVALUATES the payload against YAML policy.

    Returns JSON with:
      - violations: [ {code, text, citation?}, ... ]
      - decision_hint: "APPROVE" | "REJECT"
      - policy_source: path to YAML used (or "missing")

    This keeps the original tool name while performing evaluation.
    """
    # Guard against huge payloads
    if isinstance(extracted_json_string, str) and len(extracted_json_string.encode("utf-8")) > _MAX_INCOMING_BYTES:
        out = {
            "violations": [{"code": "PAYLOAD_TOO_LARGE", "text": "Payload exceeds limit", "citation": "size"}],
            "decision_hint": "REJECT",
            "policy_source": "n/a",
        }
        return json.dumps(out, ensure_ascii=False, indent=2)

    # Load rules (with hot reload)
    rules, src = _get_rules_hot(org_id)
    if rules is None:
        out = {
            "violations": [{"code": "POLICY_NOT_FOUND", "text": f"No YAML found for org '{org_id}'", "citation": "rules"}],
            "decision_hint": "REJECT",
            "policy_source": "missing",
        }
        return json.dumps(out, ensure_ascii=False, indent=2)

    payload = _parse_payload(extracted_json_string)
    violations: List[Dict[str, str]] = []

    # --- JSON Schema (derived from YAML; ALWAYS ON, non-fatal) ---
    schema = _build_schema_from_rules(rules) if len(rules) > 0 else _base_schema()
    try:
        json_validate(instance=payload, schema=schema)
    except SchemaError as exc:
        _add(violations, "SCHEMA_INVALID", str(exc).splitlines()[0], "schema")

    # --- Dynamic policy checks (run only if YAML key exists) ---
    name = payload.get("name")
    dob = payload.get("dob")
    idn = payload.get("id_number")
    addr = payload.get("address")

    # NAME
    if rules.get("require_name") and not name:
        _add(violations, "NAME_MISSING", "Name is required", "require_name")
    if name:
        nmin = rules.get("name_min_len")
        nmax = rules.get("name_max_len")
        if isinstance(nmin, int) and len(name) < nmin:
            _add(violations, "NAME_TOO_SHORT", f"Name shorter than {nmin}", "name_min_len")
        if isinstance(nmax, int) and len(name) > nmax:
            _add(violations, "NAME_TOO_LONG", f"Name longer than {nmax}", "name_max_len")
        rx_name = _safe_regex(rules.get("name_allow_regex"))
        if rx_name and not rx_name.match(name):
            _add(violations, "NAME_INVALID_CHARS", "Invalid characters in name", "name_allow_regex")

    # DOB / AGE
    if rules.get("require_dob") and not dob:
        _add(violations, "DOB_MISSING", "DOB is required (YYYY-MM-DD)", "require_dob")
    if dob:
        age = _calc_age(dob)
        if age is None:
            _add(violations, "DOB_INVALID", "DOB must be a real date in YYYY-MM-DD", "require_dob")
        else:
            amin = rules.get("min_age")
            amax = rules.get("max_age")
            if isinstance(amin, int) and age < amin:
                _add(violations, "AGE_TOO_LOW", f"Age {age} < min {amin}", "min_age")
            if isinstance(amax, int) and amax and age > amax:
                _add(violations, "AGE_TOO_HIGH", f"Age {age} > max {amax}", "max_age")

    # ID NUMBER
    if rules.get("require_id_number") and not idn:
        _add(violations, "ID_MISSING", "ID number is required", "require_id_number")
    if idn:
        imin = rules.get("id_min_len")
        imax = rules.get("id_max_len")
        if isinstance(imin, int) and imin and len(idn) < imin:
            _add(violations, "ID_TOO_SHORT", f"ID shorter than {imin}", "id_min_len")
        if isinstance(imax, int) and imax and len(idn) > imax:
            _add(violations, "ID_TOO_LONG", f"ID longer than {imax}", "id_max_len")
        rx_id = _safe_regex(rules.get("id_allow_regex"))
        if rx_id and not rx_id.fullmatch(idn):
            _add(violations, "ID_INVALID_CHARS", "Invalid characters/format in ID", "id_allow_regex")

    # ADDRESS
    if rules.get("require_address") and not addr:
        _add(violations, "ADDR_MISSING", "Address is required", "require_address")
    if addr:
        amin = rules.get("address_min_len")
        wmin = rules.get("address_min_words")
        rx_addr = _safe_regex(rules.get("address_allow_regex"))
        if isinstance(amin, int) and amin and len(addr) < amin:
            _add(violations, "ADDR_TOO_SHORT", f"Address shorter than {amin} characters", "address_min_len")
        if isinstance(wmin, int) and wmin and _count_words(addr) < wmin:
            _add(violations, "ADDR_TOO_FEW_WORDS", f"Address has fewer than {wmin} words", "address_min_words")
        if rx_addr and not rx_addr.fullmatch(addr):
            _add(violations, "ADDR_INVALID_CHARS", "Invalid characters in address", "address_allow_regex")

    result: Dict[str, Any] = {
        "violations": violations,
        "decision_hint": ("REJECT" if violations else "APPROVE"),
        "policy_source": src or "unknown",
    }

    # --- Runlog envelope ---
    out_dir = os.getenv("RUNLOG_DIR")
    filename = os.getenv("RUNLOG_FILE")
    if out_dir and filename:
        result_with_envelope = dict(result)
        result_with_envelope["payload_json"] = result
        result_with_envelope["out_dir"] = out_dir
        result_with_envelope["filename"] = filename
        return json.dumps(result_with_envelope, ensure_ascii=False, indent=2)

    return json.dumps(result, ensure_ascii=False, indent=2)
