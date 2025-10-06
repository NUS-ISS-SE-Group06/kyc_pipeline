import os
from typing import Optional
from crewai import LLM
import requests
from openai import OpenAI



def _ping_ollama(base_url: str, timeout=2) -> bool:
    """Ping Ollama server health endpoint."""
    try:
        r = requests.get(f"{base_url}/api/tags", timeout=timeout)
        if r.status_code == 200:
            return True
        else:
            raise RuntimeError(f"Ping test failed: HTTP {r.status_code}")
    except Exception as e:
        raise RuntimeError(f"Ping test failed: {e}")


def _ping_openai(model: str) -> bool:
    """Ping OpenAI model with minimal request."""
    try:
        client = OpenAI()
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            temperature=0,
            )
        return bool(resp and resp.choices)
    except Exception as e:
        raise RuntimeError(f"OpenAI Ping test failed: {e}")

def llmrouter(model_name: str = "gpt-5-nano", temperature: float = 0.05) -> LLM:
    """
    Simple LLM Router:
        - If model_name matches a known option, return that model.
        - Otherwise default to gpt-4o-mini
        - If any error occurs, fall back to gpt-4.1-mini"
    """
    
    fallback_model_name="gpt-4.1-mini"
    ollama_base = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    ollama_model = os.getenv("OLLAMA_MODEL", "llama3")
    try:

        # 1️⃣ Try Ollama first
        if _ping_ollama(ollama_base):
            print(f"🦙 Using local Ollama model: {ollama_model}")
            return LLM(
                model=f"ollama/{ollama_model}",
                base_url=ollama_base,
                temperature=temperature,
            )
        # Default: Openai GPT
        #gpt-4o-mini   1M Token, Input $ 0.15 Output $0.6
        #gpt-4.1-mini  1M Token, Input $ 0.4 Output $1.6
        #gpt-5-nano    1M Token, Input $ 0.05 Output $0.4
        _ping_openai(model_name)
        return LLM(
            model=model_name,
            temperature=temperature,
        )
        
    # Fallback
    except Exception:
        return LLM(
            model=fallback_model_name,
            temperature=temperature,
        )
