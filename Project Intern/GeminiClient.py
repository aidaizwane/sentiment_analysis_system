import os
import re
import time
import random
from google import genai
from Config import API_KEY

if not API_KEY:
    raise RuntimeError("GEMINI_API_KEY not found in environment.")

client = genai.Client(api_key=API_KEY)

_RETRY_SECONDS_RE = re.compile(r"retry in\s+([\d.]+)\s*s", re.IGNORECASE)
_RETRY_DELAY_JSON_RE = re.compile(r"'retryDelay'\s*:\s*'(\d+)s'", re.IGNORECASE)

def _extract_retry_seconds(err_text: str):
    m = _RETRY_SECONDS_RE.search(err_text)
    if m:
        try:
            return float(m.group(1))
        except Exception:
            pass

    m2 = _RETRY_DELAY_JSON_RE.search(err_text)
    if m2:
        try:
            return float(m2.group(1))
        except Exception:
            pass

    return None

def safe_generate_content(
    model,
    contents,
    config=None,
    *,
    max_retries: int = 8,
    base_delay: float = 3.0,
    jitter: float = 1.0
):
    """
    Robust wrapper for Gemini:
    - Retries on 503 (overloaded/unavailable) and 429 (quota/rate-limit)
    - FAIL FAST when daily quota (requests/day) is exhausted
    """
    last_exc = None

    for attempt in range(1, max_retries + 1):
        try:
            return client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )

        except Exception as e:
            last_exc = e
            err_text = str(e)
            err_lower = err_text.lower()

            retryable = (
                "503" in err_text
                or "unavailable" in err_lower
                or "overloaded" in err_lower
                or "429" in err_text
                or "resource_exhausted" in err_lower
                or "quota" in err_lower
                or "rate" in err_lower
            )

            if not retryable:
                raise

            if (
                "generaterequestsperdayperproject" in err_lower
                or "requestsperday" in err_lower
                or "per day" in err_lower
                or ("quota exceeded for metric" in err_lower and "perday" in err_lower)
            ):
                raise RuntimeError(
                    "Daily Gemini quota exhausted (requests/day). "
                    "Wait for quota reset, or enable billing / use a different project."
                ) from e

            delay = _extract_retry_seconds(err_text)
            if delay is None:
                delay = base_delay * (2 ** (attempt - 1))

            delay = delay + random.uniform(0.1, jitter)

            print(f"[Gemini Retry] {attempt}/{max_retries} sleeping {delay:.1f}s sebab: {e}")
            time.sleep(delay)

    raise last_exc

