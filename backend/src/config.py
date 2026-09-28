"""Runtime configuration for NVIDIA-backed services."""

import os

from dotenv import load_dotenv


load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
LLM_PROVIDER = os.getenv(
    "LLM_PROVIDER",
    "openrouter" if OPENROUTER_API_KEY else "gemini",
).strip().lower()
OPENROUTER_CHAT_MODEL = os.getenv("OPENROUTER_CHAT_MODEL", "openrouter/free")

# NVIDIA's current retrieval embedding model. Override only when deliberately
# migrating both indexed documents and query embeddings together.
EMBED_MODEL = os.getenv("NVIDIA_EMBED_MODEL", "nvidia/nemotron-3-embed-1b")
# Gemini powers RAG answers; NVIDIA Nemotron remains the embedding provider.
# Use a currently supported Gemini Flash model. Older names are deprecated and
# frequently return 404/503 from the Google API.
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.8-flash")
GEMINI_REQUEST_TIMEOUT_SECONDS = float(os.getenv("GEMINI_REQUEST_TIMEOUT_SECONDS", "30"))


def require_nvidia_api_key() -> str:
    """Return the API key or raise an actionable error before making a request."""
    if not NVIDIA_API_KEY:
        raise RuntimeError("NVIDIA_API_KEY is not configured. Add it to backend/.env.")
    return NVIDIA_API_KEY


def require_gemini_api_key() -> str:
    """Return the Gemini key or raise an actionable configuration error."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not configured. Add it to backend/.env.")
    return GEMINI_API_KEY


def require_openrouter_api_key() -> str:
    """Return the OpenRouter key or raise an actionable configuration error."""
    if not OPENROUTER_API_KEY:
        raise RuntimeError("OPENROUTER_API_KEY is not configured. Add it to backend/.env.")
    return OPENROUTER_API_KEY
