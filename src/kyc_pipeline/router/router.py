import os
from crewai import LLM
import requests
from openai import OpenAI

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
    
    #model_name="gpt-4.1-mini" #default to gpt-5-nano
    fallback_model_name="gpt-4o-mini"
    try:
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
