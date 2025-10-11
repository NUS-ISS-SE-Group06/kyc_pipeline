import json
import pytest
from kyc_pipeline.tools.bizrules import fetch_business_rules


@pytest.mark.parametrize("doc_type", ["passport", "id_card", "driver_license", ""])
def test_fetch_business_rules_returns_valid_json(doc_type):
    # Act
    result = fetch_business_rules.func(doc_type)  # call underlying function

    # Assert - type
    assert isinstance(result, str), "Expected a JSON string"

    # Assert - parse JSON
    parsed = json.loads(result)
    assert isinstance(parsed, dict), "Expected parsed JSON to be a dictionary"

    # Assert - check keys
    expected_keys = {"min_age", "country", "doc_required"}
    assert expected_keys.issubset(parsed.keys()), "Missing expected keys in result"

    # Assert - exact values (stub is deterministic)
    assert parsed["min_age"] == 18
    assert parsed["country"] == "SG"
    assert parsed["doc_required"] == ["passport", "photo"]


@pytest.mark.parametrize("doc_type", ["anything", "passport"])
def test_fetch_business_rules_run_matches_func_output(doc_type):
    # Tool.run simulates how CrewAI would invoke it
    via_func = fetch_business_rules.func(doc_type)
    via_run = fetch_business_rules.run(doc_type)

    # Both paths should produce the same JSON string (order-insensitive on parse)
    assert json.loads(via_func) == json.loads(via_run)
