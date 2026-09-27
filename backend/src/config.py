"""Runtime configuration for NVIDIA-backed services."""

import os

from dotenv import load_dotenv


load_dotenv()

NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY")
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# NVIDIA's current retrieval embedding model. Override only when deliberately
# migrating both indexed documents and query embeddings together.
EMBED_MODEL = os.getenv("NVIDIA_EMBED_MODEL", "nvidia/nemotron-3-embed-1b")
# Gemini powers RAG answers; NVIDIA Nemotron remains the embedding provider.
GEMINI_CHAT_MODEL = os.getenv("GEMINI_CHAT_MODEL", "gemini-3.5-flash-lite")
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
