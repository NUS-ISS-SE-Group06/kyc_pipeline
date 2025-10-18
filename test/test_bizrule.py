import json
import pytest
from kyc_pipeline.tools.bizrules import fetch_business_rules

# The tool currently ignores doc_type; keep a variety to ensure it's stable.
@pytest.mark.parametrize("doc_type", ["passport", "id_card", "driver_license", ""])
def test_fetch_business_rules_returns_valid_json(doc_type):
    # Act
    result = fetch_business_rules.run(doc_type)

    # Assert - type
    assert isinstance(result, str), "Expected the tool to return a JSON string"

    # Assert - parse JSON
    parsed = json.loads(result)
    assert isinstance(parsed, dict), "Expected parsed JSON to be a dictionary"

    # Assert - exact schema keys (strict so regressions are caught)
    expected_keys = {
        "min_age",
        "max_age",
        "require_name",
        "name_min_len",
        "name_max_len",
        "name_allow_regex",
        "require_dob",
        "require_id_number",
        "id_allow_regex",
        "id_min_len",
        "id_max_len",
        "require_address",
        "address_min_len",
        "address_min_words",
        "address_allow_regex",
    }
    assert set(parsed.keys()) == expected_keys, (
        f"Unexpected keys. Got {sorted(parsed.keys())}"
    )

    # Assert - selected exact values
    assert parsed["min_age"] == 18
    assert parsed["max_age"] == 120
    # Note: source uses string "true" not boolean True
    assert parsed["require_name"] == "true"
    assert parsed["name_min_len"] == 2
    assert parsed["name_max_len"] == 80
    # Regex strings after json.loads should have single backslashes; use r-strings
    assert parsed["name_allow_regex"] == r"^[A-Za-z][A-Za-z\-\.' ]+$"

    assert parsed["require_dob"] == "true"
    assert parsed["require_id_number"] == "true"
    assert parsed["id_allow_regex"] == r"^[A-Za-z0-9-]+$"
    assert parsed["id_min_len"] == 8
    assert parsed["id_max_len"] == 12

    assert parsed["require_address"] == "true"
    assert parsed["address_min_len"] == 10
    assert parsed["address_min_words"] == 2
    assert parsed["address_allow_regex"] == ""

    # Assert - types of key fields (to catch accidental type drift)
    int_fields = [
        "min_age",
        "max_age",
        "name_min_len",
        "name_max_len",
        "id_min_len",
        "id_max_len",
        "address_min_len",
        "address_min_words",
    ]
    for f in int_fields:
        assert isinstance(parsed[f], int), f"Field {f} should be int"

    str_fields = [
        "require_name",
        "name_allow_regex",
        "require_dob",
        "require_id_number",
        "id_allow_regex",
        "require_address",
        "address_allow_regex",
    ]
    for f in str_fields:
        assert isinstance(parsed[f], str), f"Field {f} should be str"


@pytest.mark.parametrize("a,b", [("anything", "passport"), ("", "driver_license")])
def test_fetch_business_rules_is_deterministic_and_doc_type_agnostic(a, b):
    # Tool.run should produce same JSON (order-insensitive) regardless of doc_type
    via_a = json.loads(fetch_business_rules.run(a))
    via_b = json.loads(fetch_business_rules.run(b))
    assert via_a == via_b, "Output should not depend on doc_type"

    # Also check idempotency on the same input
    via_a2 = json.loads(fetch_business_rules.run(a))
    assert via_a == via_a2, "Consecutive runs should be identical"
