from typing import Optional
from crewai import LLM
import requests

def _ping_ollama (base_url: str, timeout =2.0) -> bool:
    try:
        r = requests.get(f"{base_url}/api/tags",timeout=timeout)
        if r.status_code == 200:
            return True
        else:
            raise RuntimeError(f"Ping test failed: HTTP {r.status_code}")
    except Exception as e:
        raise RuntimeError(f"Ping test failed: {e}")


def llmrouter(model_name: Optional[str] = None, temperature: float = 0.05) -> LLM:
    """
    Simple LLM Router:
      - If model_name matches a known option, return that model.
      - Otherwise default to llama3.2:3b.
      - If any error occurs, fall back to llama3.2:1b.
    """
    try:
        if model_name and model_name.lower() == "llama3.1:8b":
            # attempt to connect to http://localhost:11434/api/tags
            url="http://localhost:11434"
            _ping_ollama(url)
            
            return LLM(
                model="llama3.1:8b",
                base_url=url,
                temperature=temperature,
            )
        elif model_name and model_name.lower() == "llama3.2:7b":
            # attempt to connect to http://localhost:11434/api/tags
            url="http://localhost:11434"
            _ping_ollama(url)

            return LLM(
                model="llama3.2:7b",
                base_url=url,
                temperature=temperature,
            )
       
        # Default LLM
        else:
            # attempt to connect to http://localhost:11434/api/tags
            url="http://localhost:11434"
            _ping_ollama(url)
            
            return LLM(
                model="ollama/llama3.2-vision:11b",
                base_url=url,
                temperature=temperature,
            )
        
    # Fallback
    except Exception:
        return LLM(
            model="ollama/llama3.2-vision:12b",
            base_url="http://localhost:11434",
            temperature=temperature,
        )
