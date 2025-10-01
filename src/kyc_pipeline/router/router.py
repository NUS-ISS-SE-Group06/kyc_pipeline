from typing import Optional
from crewai import LLM
import requests

def _ping_ollama (base_url: str, timeout =2.0) -> bool:
    try:
        r = requests.get(f"{base_url}",timeout=timeout)
        r.ok()
        return True
    except Exception as e:
        raise RuntimeError(f"Ping test failed")


def llmrouter(model_name: Optional[str] = None, temperature: float = 0.05) -> LLM:
    """
    Simple LLM Router:
      - If model_name matches a known option, return that model.
      - Otherwise default to llama3.2:3b.
      - If any error occurs, fall back to llama3.2:1b.
    """
    try:
        if model_name and model_name.lower() == "llama3.1:8b":
            llm=LLM(
                model="ollama/llama3.1:8b",
                base_url="http://localhost:11434",
                temperature=temperature,
            )
        elif model_name and model_name.lower() == "llama3.2:7b":
            llm=LLM(
                model="ollama/llama3.2:7b",
                base_url="http://localhost:11434",
                temperature=temperature,
            )
        else:
            llm= LLM(
                model="ollama/llama3.2:3b",
                base_url="http://localhost:11434",
                temperature=temperature,
            )
        _ping_ollama(llm.base_url)

    # fallback
    except Exception:
        return LLM(
            model="ollama/llama3.2:1b",
            base_url="http://localhost:11434",
            temperature=temperature,
        )
