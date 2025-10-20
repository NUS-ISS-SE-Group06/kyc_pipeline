# -*- coding: utf-8 -*-
"""
BizRules validator (YAML-driven) — single tool named 'fetch_business_rules'.

Design
------
- Policy is defined in YAML (per doc_type; fallback to non-sg-default.yaml).
- Evaluate ONLY business fields (name, dob, id_number, address, email, has_face_photo).
- Ignore known metadata (confidence, coverage_notes) BEFORE schema validation.
- Flag any other unexpected keys with SCHEMA_INVALID (additionalProperties: False).
- Keep functions small and focused (Sonar-friendly), use fullmatch for regex.
"""

from __future__ import annotations

import json
import logging
import os
import re
import unicodedata
from datetime import date, datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from crewai.tools import tool
from jsonschema import ValidationError as SchemaError
from jsonschema import validate as json_validate

# ------------------------------ Logger ---------------------------------------

LOGGER = logging.getLogger(__name__)

# ------------------------------ Constants & Cache -----------------------------

MAX_INCOMING_BYTES: int = 100_000  # payload guardrail
DOB_ISO_PATTERN: str = r"^\d{4}-\d{2}-\d{2}$"

# Treat these as SYSTEM/PIPELINE metadata, not business fields
IGNORED_METADATA: set[str] = {"confidence", "coverage_notes"}

# doc_type -> {"rules": dict, "path": str, "mtime": float}
_RULES_CACHE: Dict[str, Dict[str, Any]] = {}

# <project_root>/kyc_pipeline/config
_DEFAULT_RULES_DIR: Path = Path(__file__).resolve().parents[1] / "config"
_RULES_DIR: Path = _DEFAULT_RULES_DIR


# ------------------------------ File / Rules Helpers --------------------------

def _file_mtime(path: Path) -> Optional[float]:
    try:
        return path.stat().st_mtime
    except OSError as exc:
        LOGGER.warning("Failed to stat YAML file %s: %s", path, exc)
        return None


def _load_yaml(path: Path) -> Optional[Dict[str, Any]]:
    try:
        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data if isinstance(data, dict) else {}
    except OSError as exc:
        LOGGER.warning("Failed to load YAML %s: %s", path, exc)
        return None


def _sanitize_doc_type(doc_type: str) -> str:
    """Map raw doc_type to a safe filename stem."""
    safe = re.sub(r"[^A-Za-z0-9._-]+", "_", (doc_type or "").strip())
    return safe or "non-sg-default"


def _load_yaml_rules(doc_type: str) -> Tuple[Optional[Dict[str, Any]], Optional[str], Optional[float]]:
    """
    Try <doc_type>.yaml first, then fallback to non-sg-default.yaml.
    """
    primary = _RULES_DIR / f"{_sanitize_doc_type(doc_type)}.yaml"
    if primary.exists():
        return _load_yaml(primary), str(primary), _file_mtime(primary)

    fallback = _RULES_DIR / "non-sg-default.yaml"
    if fallback.exists():
        return _load_yaml(fallback), str(fallback), _file_mtime(fallback)

    return None, None, None


def _get_rules_hot(doc_type: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Cached load with hot-reload on mtime change (no restart needed).
    """
    rules, src, mtime = _load_yaml_rules(doc_type)
    if rules is None:
        return None, None

    cached = _RULES_CACHE.get(doc_type)
    if cached is None:
        _RULES_CACHE[doc_type] = {"rules": rules, "path": src, "mtime": mtime}
        return rules, src

    if cached.get("path") == src:
        if cached.get("mtime") != mtime:
            _RULES_CACHE[doc_type] = {"rules": rules, "path": src, "mtime": mtime}
        return _RULES_CACHE[doc_type]["rules"], _RULES_CACHE[doc_type]["path"]

    _RULES_CACHE[doc_type] = {"rules": rules, "path": src, "mtime": mtime}
    return rules, src


# ------------------------------ Utility Helpers ------------------------------

def _safe_regex(pattern: Optional[str]) -> Optional[re.Pattern[str]]:
    patt = (pattern or "").strip()
    return re.compile(patt) if patt else None


def _calc_age(iso_date: str) -> Optional[int]:
    parts = iso_date.split("-")
    if len(parts) != 3:
        return None
    try:
        year, month, day = int(parts[0]), int(parts[1]), int(parts[2])
        dob = date(year, month, day)
    except (ValueError, TypeError):
        return None
    today = date.today()
    return today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))


def _count_words(text: str) -> int:
    return len([w for w in re.split(r"\s+", (text or "").strip()) if w])


def _add(violations: List[Dict[str, str]], code: str, msg: str, citation: Optional[str] = None) -> None:
    v: Dict[str, str] = {"code": code, "text": msg}
    if citation:
        v["citation"] = citation
    violations.append(v)


def _strip_metadata(payload: Any) -> Any:
    """
    Return a shallow copy without known metadata fields (not validated by business rules).
    """
    if not isinstance(payload, dict):
        return payload
    out = dict(payload)
    for k in IGNORED_METADATA:
        out.pop(k, None)
    return out


def _norm_str(s: Optional[str]) -> Optional[str]:
    """Normalize OCR strings: NFKC + strip + remove common zero-width chars."""
    if not isinstance(s, str):
        return s
    # NFKC handles full-width variants from OCR (e.g., ＠ → @, ． → .)
    s = unicodedata.normalize("NFKC", s)
    s = s.replace("\u200b", "").replace("\u200c", "").replace("\u200d", "").replace("\ufeff", "")
    return s.strip()


# ------------------------------ Schema Builder -------------------------------

def _build_schema_from_rules(rules: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build a JSON schema dynamically from YAML rules (no hardcoded thresholds).
    If a policy knob isn't present in YAML, the schema won't enforce it.
    """
    props: Dict[str, Any] = {}

    # name
    if any(k in rules for k in ("require_name", "name_min_len", "name_max_len", "name_allow_regex")):
        name_schema: Dict[str, Any] = {"type": "string"}
        nmin = rules.get("name_min_len")
        nmax = rules.get("name_max_len")
        if isinstance(nmin, int):
            name_schema["minLength"] = nmin
        if isinstance(nmax, int):
            name_schema["maxLength"] = nmax
        props["name"] = name_schema

    # dob
    if any(k in rules for k in ("require_dob", "min_age", "max_age")):
        props["dob"] = {"type": "string", "pattern": DOB_ISO_PATTERN}

    # id_number
    if any(k in rules for k in ("require_id_number", "id_min_len", "id_max_len", "id_allow_regex")):
        id_schema: Dict[str, Any] = {"type": "string"}
        imin = rules.get("id_min_len")
        imax = rules.get("id_max_len")
        if isinstance(imin, int):
            id_schema["minLength"] = imin
        if isinstance(imax, int):
            id_schema["maxLength"] = imax
        props["id_number"] = id_schema

    # address
    if any(k in rules for k in ("require_address", "address_min_len", "address_min_words", "address_allow_regex")):
        props["address"] = {"type": "string"}

    # email
    if any(k in rules for k in ("require_email", "email_allow_regex")):
        props["email"] = {"type": "string"}

    # has_face_photo
    if rules.get("require_has_face_photo") is True:
        props["has_face_photo"] = {"type": ["boolean"]}

    # Optional: metadata pass-through (not enforced)
    props["metadata"] = {"type": "object"}

    return {
        "type": "object",
        "properties": props,
        # STRICT: any property not defined above will cause SCHEMA_INVALID
        "additionalProperties": False,
    }


@lru_cache(maxsize=1)
def _base_schema() -> Dict[str, Any]:
    return {"type": "object", "properties": {"metadata": {"type": "object"}}, "additionalProperties": False}


def _parse_payload(extracted_json_string: Any) -> Dict[str, Any]:
    if isinstance(extracted_json_string, dict):
        return extracted_json_string
    if isinstance(extracted_json_string, list):
        return {"payload": extracted_json_string}
    if not isinstance(extracted_json_string, str):
        raise TypeError("extracted_json_string must be str|dict|list")
    obj = json.loads(extracted_json_string)
    if not isinstance(obj, dict):
        raise ValueError("Top-level JSON must be an object")
    return obj


# ------------------------------ Field Checks (helpers) ------------------------

def _check_name(rules: Dict[str, Any], name: Optional[str], violations: List[Dict[str, str]]) -> None:
    if rules.get("require_name") and not name:
        _add(violations, "NAME_MISSING", "Name is required", "require_name")
        return
    if not name:
        return
    nmin = rules.get("name_min_len")
    nmax = rules.get("name_max_len")
    if isinstance(nmin, int) and len(name) < nmin:
        _add(violations, "NAME_TOO_SHORT", f"Name shorter than {nmin}", "name_min_len")
    if isinstance(nmax, int) and len(name) > nmax:
        _add(violations, "NAME_TOO_LONG", f"Name longer than {nmax}", "name_max_len")
    rx_name = _safe_regex(rules.get("name_allow_regex"))
    if rx_name and not rx_name.fullmatch(name):
        _add(violations, "NAME_INVALID_CHARS", "Invalid characters in name", "name_allow_regex")


def _check_dob_and_age(rules: Dict[str, Any], dob: Optional[str], violations: List[Dict[str, str]]) -> None:
    if rules.get("require_dob") and not dob:
        _add(violations, "DOB_MISSING", "DOB is required (YYYY-MM-DD)", "require_dob")
        return
    if not dob:
        return
    if not re.fullmatch(DOB_ISO_PATTERN, dob):
        _add(violations, "DOB_INVALID", "DOB must be a real date in YYYY-MM-DD", "require_dob")
        return
    age = _calc_age(dob)
    if age is None:
        _add(violations, "DOB_INVALID", "DOB must be a real date in YYYY-MM-DD", "require_dob")
        return
    amin = rules.get("min_age")
    amax = rules.get("max_age")
    if isinstance(amin, int) and age < amin:
        _add(violations, "AGE_TOO_LOW", f"Age {age} < min {amin}", "min_age")
    if isinstance(amax, int) and age > amax:
        _add(violations, "AGE_TOO_HIGH", f"Age {age} > max {amax}", "max_age")


def _check_id(rules: Dict[str, Any], idn: Optional[str], violations: List[Dict[str, str]]) -> None:
    if rules.get("require_id_number") and not idn:
        _add(violations, "ID_MISSING", "ID number is required", "require_id_number")
        return
    if not idn:
        return
    imin = rules.get("id_min_len")
    imax = rules.get("id_max_len")
    if isinstance(imin, int) and len(idn) < imin:
        _add(violations, "ID_TOO_SHORT", f"ID shorter than {imin}", "id_min_len")
    if isinstance(imax, int) and len(idn) > imax:
        _add(violations, "ID_TOO_LONG", f"ID longer than {imax}", "id_max_len")
    rx_id = _safe_regex(rules.get("id_allow_regex"))
    if rx_id and not rx_id.fullmatch(idn):
        _add(violations, "ID_INVALID_CHARS", "Invalid characters/format in ID", "id_allow_regex")


def _check_address(rules: Dict[str, Any], addr: Optional[str], violations: List[Dict[str, str]]) -> None:
    if rules.get("require_address") and not addr:
        _add(violations, "ADDR_MISSING", "Address is required", "require_address")
        return
    if not addr:
        return
    amin = rules.get("address_min_len")
    wmin = rules.get("address_min_words")
    rx_addr = _safe_regex(rules.get("address_allow_regex"))
    if isinstance(amin, int) and len(addr) < amin:
        _add(violations, "ADDR_TOO_SHORT", f"Address shorter than {amin} characters", "address_min_len")
    if isinstance(wmin, int) and _count_words(addr) < wmin:
        _add(violations, "ADDR_TOO_FEW_WORDS", f"Address has fewer than {wmin} words", "address_min_words")
    if rx_addr and not rx_addr.fullmatch(addr):
        _add(violations, "ADDR_INVALID_CHARS", "Invalid characters in address", "address_allow_regex")


def _check_email(rules: Dict[str, Any], email: Optional[str], violations: List[Dict[str, str]]) -> None:
    if rules.get("require_email") and not email:
        _add(violations, "EMAIL_MISSING", "Email is required", "require_email")
        return
    if not email:
        return
    rx_email = _safe_regex(rules.get("email_allow_regex"))
    if rx_email and not rx_email.fullmatch(email):
        _add(violations, "EMAIL_INVALID", "Email format is invalid", "email_allow_regex")


def _check_face_photo(rules: Dict[str, Any], face: Any, violations: List[Dict[str, str]]) -> None:
    if rules.get("require_has_face_photo") is True and face is not True:
        _add(violations, "FACE_PHOTO_REQUIRED", "Face photo is required (boolean true)", "require_has_face_photo")


# ------------------------------ Single Tool ----------------------------------

@tool("fetch_business_rules")
def fetch_business_rules(doc_type: str, extracted_json_string: str) -> str:
    """
    Evaluate the payload against YAML policy **for the given doc_type**.

    Returns JSON:
      - violations: [ {code, text, citation?}, ... ]
      - decision_hint: "APPROVE" | "REJECT"
      - policy_source: path to YAML used (or "missing")
      - created_at: ISO8601 UTC timestamp
      - modified_at: ISO8601 UTC timestamp
    """
    # Size guard (defensive)
    if isinstance(extracted_json_string, str) and len(extracted_json_string.encode("utf-8")) > MAX_INCOMING_BYTES:
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        out = {
            "violations": [{"code": "PAYLOAD_TOO_LARGE", "text": "Payload exceeds limit", "citation": "size"}],
            "decision_hint": "REJECT",
            "policy_source": "n/a",
            "created_at": now_iso,
            "modified_at": now_iso,
        }
        return json.dumps(out, ensure_ascii=False, indent=2)

    # Load rules (with hot reload)
    rules, src = _get_rules_hot(doc_type)
    if rules is None:
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        out = {
            "violations": [{"code": "POLICY_NOT_FOUND", "text": f"No YAML found for doc_type '{doc_type}'", "citation": "rules"}],
            "decision_hint": "REJECT",
            "policy_source": "missing",
            "created_at": now_iso,
            "modified_at": now_iso,
        }
        return json.dumps(out, ensure_ascii=False, indent=2)

    # Parse JSON input
    try:
        raw_payload = _parse_payload(extracted_json_string)
    except (TypeError, ValueError) as exc:
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        out = {
            "violations": [{"code": "PAYLOAD_INVALID_JSON", "text": str(exc), "citation": "json"}],
            "decision_hint": "REJECT",
            "policy_source": src or "unknown",
            "created_at": now_iso,
            "modified_at": now_iso,
        }
        return json.dumps(out, ensure_ascii=False, indent=2)

    # Drop metadata fields so strict schema won't flag them
    payload = _strip_metadata(raw_payload)

    # Normalize common string fields (avoid OCR whitespace/zero-width/full-width chars)
    for key in ("name", "dob", "id_number", "address", "email"):
        if key in payload:
            payload[key] = _norm_str(payload.get(key))

    violations: List[Dict[str, str]] = []

    # JSON Schema (derived from YAML; always-on, non-fatal)
    schema = _build_schema_from_rules(rules) if len(rules) > 0 else _base_schema()
    try:
        json_validate(instance=payload, schema=schema)
    except SchemaError as exc:
        _add(violations, "SCHEMA_INVALID", str(exc).splitlines()[0], "schema")

    # Field values
    name = payload.get("name")
    dob = payload.get("dob")
    idn = payload.get("id_number")
    addr = payload.get("address")
    email = payload.get("email")
    face = payload.get("has_face_photo")

    # Policy checks (helpers)
    _check_name(rules, name, violations)
    _check_dob_and_age(rules, dob, violations)
    _check_id(rules, idn, violations)
    _check_address(rules, addr, violations)
    _check_email(rules, email, violations)
    _check_face_photo(rules, face, violations)

    # Build result
    result: Dict[str, Any] = {
        "violations": violations,
        "decision_hint": ("REJECT" if violations else "APPROVE"),
        "policy_source": src or "unknown",
    }

    # --- Ensure downstream tools have required timestamps ---
    # Prefer values from incoming payload.metadata, else backfill with now (UTC).
    try:
        meta_in: Dict[str, Any] = {}
        if isinstance(raw_payload, dict):
            meta_in = raw_payload.get("metadata") or {}
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        result["created_at"] = meta_in.get("created_at") or now_iso
        result["modified_at"] = meta_in.get("modified_at") or now_iso
    except (TypeError, ValueError, AttributeError) as exc:
        LOGGER.warning("Failed to decorate timestamps from payload metadata: %s", exc)
        now_iso = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")
        result["created_at"] = result.get("created_at") or now_iso
        result["modified_at"] = result.get("modified_at") or now_iso

    # Optional runlog envelope passthrough
    out_dir = os.getenv("RUNLOG_DIR")
    filename = os.getenv("RUNLOG_FILE")
    if out_dir and filename:
        result_with_envelope = dict(result)
        result_with_envelope["payload_json"] = result
        result_with_envelope["out_dir"] = out_dir
        result_with_envelope["filename"] = filename
        # duplicate timestamps at top-level for consumers that read the envelope root
        result_with_envelope["created_at"] = result["created_at"]
        result_with_envelope["modified_at"] = result["modified_at"]
        return json.dumps(result_with_envelope, ensure_ascii=False, indent=2)

    return json.dumps(result, ensure_ascii=False, indent=2)
