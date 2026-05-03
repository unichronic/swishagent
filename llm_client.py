import os
import time
from pathlib import Path

from dotenv import load_dotenv
from google import genai as google_genai
from openai import OpenAI, RateLimitError
from tracing import langfuse_observation

load_dotenv(Path(__file__).resolve().with_name(".env"))

_TEXT_PROVIDERS = [
    {"name": "mistral",    "base_url": "https://api.mistral.ai/v1",                               "key_env": "MISTRAL_API_KEY",    "model": "mistral-large-latest"},
    {"name": "nvidia",     "base_url": "https://integrate.api.nvidia.com/v1",                     "key_env": "NVIDIA_API_KEY",     "model": "meta/llama-3.3-70b-instruct"},
    {"name": "groq_gpt",   "base_url": "https://api.groq.com/openai/v1",                          "key_env": "GROQ_API_KEY",       "model": "openai/gpt-oss-20b"},
    {"name": "groq_qwen",  "base_url": "https://api.groq.com/openai/v1",                          "key_env": "GROQ_API_KEY",       "model": "qwen/qwen3-32b"},
    {"name": "openrouter", "base_url": "https://openrouter.ai/api/v1",                            "key_env": "OPENROUTER_API_KEY", "model": "meta-llama/llama-3.3-70b-instruct:free"},
]

def _get_gemini_keys():
    return [k for k in [
        os.getenv("GEMINI_API_KEY_1"),
        os.getenv("GEMINI_API_KEY_2"),
        os.getenv("GEMINI_API_KEY_3"),
    ] if k]

# separate indices so text and multimodal rotations don't interfere
_gemini_text_idx = 0
_gemini_mm_idx = 0

# tracks which text provider is currently healthy for Agno's Agent
_primary_provider_idx = 0  # Will be set to first available provider

# Track rate-limited providers with cooldown time
_rate_limited_providers = {}  # {provider_name: cooldown_until_timestamp}

def call_text(messages: list, **kwargs) -> str:
    """Tier 1: try text providers in order, fall back to Gemini only if all fail."""
    global _primary_provider_idx, _rate_limited_providers
    trace_name = kwargs.pop("trace_name", "llm.call_text")
    trace_metadata = kwargs.pop("trace_metadata", {})
    
    current_time = time.time()
    
    for i, p in enumerate(_TEXT_PROVIDERS):
        # Skip if provider is in cooldown
        if p["name"] in _rate_limited_providers:
            if current_time < _rate_limited_providers[p["name"]]:
                print(f"[llm] {p['name']} in cooldown, skipping...")
                continue
            else:
                # Cooldown expired, remove from list
                del _rate_limited_providers[p["name"]]
        
        key = os.getenv(p["key_env"])
        if not key:
            continue
        try:
            with langfuse_observation(
                trace_name,
                as_type="generation",
                model=p["model"],
                input={"messages": messages, "parameters": kwargs},
                metadata={**trace_metadata, "provider": p["name"], "base_url": p["base_url"]},
            ) as generation:
                client = OpenAI(base_url=p["base_url"], api_key=key)
                resp = client.chat.completions.create(model=p["model"], messages=messages, **kwargs)
                content = resp.choices[0].message.content
                usage = getattr(resp, "usage", None)
                usage_details = None
                if usage:
                    usage_details = {
                        "input_tokens": getattr(usage, "prompt_tokens", None),
                        "output_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    }
                generation.update(output=content, usage_details=usage_details)
            _primary_provider_idx = i  # remember last working provider
            return content
        except RateLimitError as e:
            print(f"[llm] {p['name']} rate limited, trying next...")
            # Add to cooldown for 5 minutes
            _rate_limited_providers[p["name"]] = current_time + 300
        except Exception as e:
            print(f"[llm] {p['name']} error: {e}, trying next...")

    print("[llm] all text providers exhausted, falling back to Gemini")
    return _call_gemini_text(messages, trace_name=trace_name, trace_metadata=trace_metadata, **kwargs)


def call_text_judge(messages: list) -> str:
    """
    LLM-as-Judge: Explicitly use Mistral for semantic detection.
    Separate from main agent to allow different provider selection.
    """
    import sys
    
    # Try Mistral first
    mistral_key = os.getenv("MISTRAL_API_KEY")
    if mistral_key:
        try:
            print(f"[llm-judge] Using Mistral", file=sys.stderr, flush=True)
            client = OpenAI(base_url="https://api.mistral.ai/v1", api_key=mistral_key)
            resp = client.chat.completions.create(model="mistral-medium-2505", messages=messages)
            return resp.choices[0].message.content
        except RateLimitError:
            print(f"[llm-judge] Mistral rate limited, falling back...", file=sys.stderr, flush=True)
        except Exception as e:
            print(f"[llm-judge] Mistral error: {e}, falling back...", file=sys.stderr, flush=True)
    
    # Fallback to Nvidia
    nvidia_key = os.getenv("NVIDIA_API_KEY")
    if nvidia_key:
        try:
            print(f"[llm-judge] Using Nvidia", file=sys.stderr, flush=True)
            client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=nvidia_key)
            resp = client.chat.completions.create(model="meta/llama-3.3-70b-instruct", messages=messages)
            return resp.choices[0].message.content
        except Exception as e:
            print(f"[llm-judge] Nvidia error: {e}, falling back to Gemini...", file=sys.stderr, flush=True)
    
    # Final fallback to Gemini
    print("[llm-judge] Using Gemini", file=sys.stderr, flush=True)
    return _call_gemini_text(messages)


def _call_gemini_text(messages: list, **kwargs) -> str:
    global _gemini_text_idx
    trace_name = kwargs.pop("trace_name", "llm.gemini_text")
    trace_metadata = kwargs.pop("trace_metadata", {})
    keys = _get_gemini_keys()
    if not keys:
        raise RuntimeError("No Gemini keys configured")
    gemini_kwargs = {}
    if "temperature" in kwargs:
        gemini_kwargs["temperature"] = kwargs["temperature"]
    for _ in range(len(keys)):
        try:
            with langfuse_observation(
                trace_name,
                as_type="generation",
                model="gemini-2.5-flash",
                input={"messages": messages, "parameters": gemini_kwargs},
                metadata={**trace_metadata, "provider": "gemini", "key_index": _gemini_text_idx},
            ) as generation:
                client = OpenAI(
                    base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                    api_key=keys[_gemini_text_idx % len(keys)]
                )
                resp = client.chat.completions.create(model="gemini-2.5-flash", messages=messages, **gemini_kwargs)
                content = resp.choices[0].message.content
                usage = getattr(resp, "usage", None)
                usage_details = None
                if usage:
                    usage_details = {
                        "input_tokens": getattr(usage, "prompt_tokens", None),
                        "output_tokens": getattr(usage, "completion_tokens", None),
                        "total_tokens": getattr(usage, "total_tokens", None),
                    }
                generation.update(output=content, usage_details=usage_details)
                return content
        except RateLimitError:
            print(f"[llm] Gemini text key {_gemini_text_idx+1} quota hit, rotating...")
            _gemini_text_idx = (_gemini_text_idx + 1) % len(keys)
        except Exception as e:
            print(f"[llm] Gemini text key {_gemini_text_idx+1} error: {e}")
            _gemini_text_idx = (_gemini_text_idx + 1) % len(keys)
    raise RuntimeError("All Gemini text keys exhausted")


def get_primary_model_config() -> dict:
    """Returns the current healthy provider config for Agno's OpenAILike model."""
    global _rate_limited_providers, _primary_provider_idx
    
    import sys
    print(f"[llm] get_primary_model_config called, _primary_provider_idx={_primary_provider_idx}", file=sys.stderr, flush=True)
    print(f"[llm] Rate-limited providers: {list(_rate_limited_providers.keys())}", file=sys.stderr, flush=True)
    
    current_time = time.time()
    
    # Try each provider starting from the last successful one
    for offset in range(len(_TEXT_PROVIDERS)):
        i = (_primary_provider_idx + offset) % len(_TEXT_PROVIDERS)
        p = _TEXT_PROVIDERS[i]
        
        print(f"[llm] Checking provider {i}: {p['name']}", file=sys.stderr, flush=True)
        
        # Skip if provider is in cooldown
        if p["name"] in _rate_limited_providers:
            if current_time < _rate_limited_providers[p["name"]]:
                print(f"[llm] {p['name']} in cooldown, skipping for agent...", file=sys.stderr, flush=True)
                continue
            else:
                # Cooldown expired, remove from list
                del _rate_limited_providers[p["name"]]
                print(f"[llm] {p['name']} cooldown expired", file=sys.stderr, flush=True)
        
        key = os.getenv(p["key_env"])
        if key:
            print(f"[llm] ✅ Using {p['name']} for agent", file=sys.stderr, flush=True)
            _primary_provider_idx = i
            return {"base_url": p["base_url"], "api_key": key, "model": p["model"]}
        else:
            print(f"[llm] {p['name']} has no API key", file=sys.stderr, flush=True)
    
    # All providers are rate-limited or unavailable, fall back to Gemini
    print("[llm] All providers unavailable, using Gemini for agent", file=sys.stderr, flush=True)
    keys = _get_gemini_keys()
    key = keys[_gemini_text_idx % len(keys)] if keys else None
    return {"base_url": "https://generativelanguage.googleapis.com/v1beta/openai/", "api_key": key, "model": "gemini-2.5-flash"}


def mark_provider_rate_limited():
    """Mark the current primary provider as rate-limited for 5 minutes"""
    import sys
    global _rate_limited_providers, _primary_provider_idx
    
    if _primary_provider_idx < len(_TEXT_PROVIDERS):
        p = _TEXT_PROVIDERS[_primary_provider_idx]
        current_time = time.time()
        _rate_limited_providers[p["name"]] = current_time + 300  # 5 minutes cooldown
        print(f"[llm] Marked {p['name']} as rate-limited for 5 minutes", file=sys.stderr, flush=True)
    else:
        print("[llm] Cannot mark provider as rate-limited (using Gemini)", file=sys.stderr, flush=True)


def call_gemini_multimodal(contents: list):
    """Multimodal call for image analysis. Independent key rotation from text."""
    global _gemini_mm_idx
    keys = _get_gemini_keys()
    if not keys:
        raise RuntimeError("No Gemini keys configured")
    for _ in range(len(keys)):
        try:
            client = google_genai.Client(api_key=keys[_gemini_mm_idx % len(keys)])
            return client.models.generate_content(model="gemini-2.5-flash", contents=contents)
        except Exception as e:
            if "429" in str(e) or "quota" in str(e).lower() or "RESOURCE_EXHAUSTED" in str(e):
                print(f"[llm] Gemini multimodal key {_gemini_mm_idx+1} quota hit, rotating...")
                _gemini_mm_idx = (_gemini_mm_idx + 1) % len(keys)
            else:
                raise
    raise RuntimeError("All Gemini multimodal keys exhausted")
