import os
from dotenv import load_dotenv
import anthropic

load_dotenv()

# Model tiers — use Haiku for memos (3 calls, speed matters)
_HAIKU   = "claude-haiku-4-5-20251001"
_SONNET  = "claude-sonnet-4-6"

def call_llm(prompt: str, *, model: str = _HAIKU, max_tokens: int = 1500) -> str:
    """
    Call the Anthropic API. Raises a clear RuntimeError on auth / model errors
    so the caller can surface a structured 500, not a cryptic stack trace.
    """
    key = os.getenv("ANTHROPIC_API_KEY")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set in environment")
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
