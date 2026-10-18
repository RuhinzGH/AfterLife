"""A small client for Groq's chat API, used only to *word* explanations.

The language model never sets a number: every figure on the page is computed in
code first, and afterlife/explain.py checks that every number the model writes
was in what it was given. The key is read at run time (GROQ_API_KEY, from the
environment or the git-ignored .env), never stored in the code.
"""
from __future__ import annotations

import requests

from .config import secret

ENDPOINT = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"
#: A short answer from a fast provider; one that has not arrived by now will
#: not, and the rule-based summary is already on the page.
TIMEOUT_S = 12


def available() -> bool:
    return bool(secret("GROQ_API_KEY"))


def model() -> str:
    return secret("GROQ_MODEL") or DEFAULT_MODEL


def chat(system: str, user: str, *, temperature: float = 0.3, max_tokens: int = 700) -> str:
    """The model's reply text. Raises on any failure; callers fall back."""
    key = secret("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is not set")
    body = {
        "model": model(),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if model().startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"     # keep its thinking short so the answer fits
    resp = requests.post(ENDPOINT, json=body, timeout=TIMEOUT_S,
                         headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"})
    resp.raise_for_status()
    text = (resp.json()["choices"][0]["message"].get("content") or "").strip()
    if not text:
        raise RuntimeError("empty reply")
    return text


def describe_error(exc: Exception) -> str:
    """Short and diagnostic: a bad key, a rate limit and an outage need different fixes."""
    resp = getattr(exc, "response", None)
    if resp is not None:
        reason = {401: "invalid API key", 429: "rate limited", 503: "service unavailable"}.get(resp.status_code, "")
        return f"HTTP {resp.status_code}" + (f" ({reason})" if reason else "")
    return type(exc).__name__
