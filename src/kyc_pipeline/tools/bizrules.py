from crewai.tools import tool
import json

@tool("fetch_business_rules")
def fetch_business_rules(doc_type: str) -> str:
    """Return org rules JSON (stub)."""
    data = { "min_age": 18,
             "max_age": 120,
              "require_name": "true",
              "name_min_len": 2,
              "name_max_len": 80,
              "name_allow_regex": "^[A-Za-z][A-Za-z\\-\\.' ]+$",
              "require_dob": "true",
              "require_id_number": "true",
              "id_allow_regex": "^[A-Za-z0-9-]+$",
              "id_min_len": 8,                  
              "id_max_len": 12,                    
              "require_address": "true",
              "address_min_len": 10,
              "address_min_words": 2,
              "address_allow_regex": "",  
            }
    return json.dumps(data)
