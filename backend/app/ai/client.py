import os
import logging
from dotenv import load_dotenv
import anthropic

load_dotenv()

logger = logging.getLogger(__name__)

# Model tiers — use Haiku for memos (3 calls, speed matters)
_HAIKU   = "claude-haiku-4-5-20251001"
_SONNET  = "claude-sonnet-4-6"

# The model call_llm() uses when the caller does not name one. Callers that
# record which model produced a stored artefact MUST report the model they
# actually passed — never a hardcoded string, which silently goes stale.
DEFAULT_MODEL = _HAIKU

# Substrings that mark a copied-from-.env.example placeholder rather than a key.
_PLACEHOLDER_MARKERS = (
    "your_", "your-", "yourkey", "xxx", "changeme", "change_me",
    "replace", "placeholder", "actual_key", "here",
)
_MIN_KEY_LEN = 40   # real Anthropic keys are ~100 chars; .env.example stubs are ~20-30


def validate_api_key(key: str | None) -> str:
    """
    Return a usable ANTHROPIC_API_KEY or raise RuntimeError explaining exactly
    what is wrong.

    A placeholder is worse than a missing key: `if not key` passes, the SDK is
    called, and the operator sees a generic auth error instead of "you never
    filled this in". Prod ran for weeks with a 28-char
    'sk-ant-api03-YOUR_ACTUAL...' stub for this reason.
    """
    if not key or not key.strip():
        raise RuntimeError(
            "ANTHROPIC_API_KEY not set. Add it to backend/.env and restart the service."
        )
    key = key.strip()
    low = key.lower()
    if any(m in low for m in _PLACEHOLDER_MARKERS):
        raise RuntimeError(
            "ANTHROPIC_API_KEY is still the .env.example placeholder, not a real key. "
            "Replace it in backend/.env and restart the service."
        )
    if len(key) < _MIN_KEY_LEN:
        raise RuntimeError(
            f"ANTHROPIC_API_KEY looks truncated ({len(key)} chars; expected "
            f"{_MIN_KEY_LEN}+). Check backend/.env for a partial paste."
        )
    if not key.startswith("sk-ant-"):
        raise RuntimeError(
            "ANTHROPIC_API_KEY does not start with 'sk-ant-'. Check backend/.env."
        )
    return key


def startup_check() -> bool:
    """
    Validate the AI key at boot and log the exact problem.

    Deliberately does NOT raise. The AI memo is an optional explanation layer
    (see CLAUDE.md 2.2 — AI is never in the core math path); a missing key must
    not take down auth, uploads or analytics. Returns True when usable.
    """
    try:
        validate_api_key(os.getenv("ANTHROPIC_API_KEY"))
        logger.info("ANTHROPIC_API_KEY validated — AI memo available")
        return True
    except RuntimeError as e:
        logger.error("AI memo DISABLED — %s", e)
        return False


def call_llm(prompt: str, *, model: str = DEFAULT_MODEL, max_tokens: int = 1500) -> str:
    """
    Call the Anthropic API. Raises a clear RuntimeError on auth / model errors
    so the caller can surface a structured 500, not a cryptic stack trace.
    """
    key = validate_api_key(os.getenv("ANTHROPIC_API_KEY"))
    try:
        c = anthropic.Anthropic(api_key=key)
        m = c.messages.create(
            model=model,
            max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}],
        )
        return m.content[0].text
    except anthropic.AuthenticationError:
        raise RuntimeError("Anthropic API key is invalid or expired")
    except anthropic.NotFoundError as e:
        raise RuntimeError(f"Model not found: {model} — {e}")
    except Exception as e:
        raise RuntimeError(f"LLM call failed: {e}")
