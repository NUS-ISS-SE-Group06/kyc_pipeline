from typing import Optional
from crewai import LLM
import requests
from openai import OpenAI

client = OpenAI()

def _ping_ollama (base_url: str, timeout =2.0) -> bool:
    """Ping Ollama server health endpoint."""
    try:
        r = requests.get(f"{base_url}/api/tags",timeout=timeout)
        if r.status_code == 200:
            return True
        else:
            raise RuntimeError(f"Ping test failed: HTTP {r.status_code}")
    except Exception as e:
        raise RuntimeError(f"Ping test failed: {e}")


def _ping_openai (model: str) -> bool:
     """Ping OpenAI model with minimal request."""
     try:
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
         )
        return bool(resp and resp.choices)
     except Exception as e:
         raise RuntimeError(f"OpenAI Ping test failed: {e}")

def llmrouter(model_name: Optional[str] = None, temperature: float = 0.05) -> LLM:
    """
    Simple LLM Router:
      - If model_name matches a known option, return that model.
      - Otherwise default to gpt-4o-mini
      - If any error occurs, fall back to llama3.2-vision:11b
    """
    try:
        url="http://localhost:11434"

        if model_name:
            alias = model_name.lower()
            if alias in ["llama3.1:8b", "llama3.2:7b", "llama3.2-vision:11b"]:
                _ping_ollama(url)
                return LLM(
                    model=f"ollama/{alias}",
                    base_url=url,
                    temperature=temperature,
                )
            
        # Default: Openai GPT
        alias="gpt-4o-mini"
        if model_name:
            alias = model_name.lower()
        _ping_openai(alias)

        return LLM(
            model=alias,
            temperature=temperature,
        )
        
    # Fallback
    except Exception:
        return LLM(
            model="ollama/llama3.2-vision:11b",
            base_url=url,
            temperature=temperature,
        )
