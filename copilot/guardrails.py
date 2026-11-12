"""Lightweight guardrails. Real deployments add a moderation API, PII detection and policy engines."""
from __future__ import annotations

import re

MAX_INPUT_CHARS = 2000

_INJECTION_PATTERNS = [
    r"ignore (all |any )?(previous|prior|above) (instructions|rules)",
    r"(reveal|show|print).{0,20}(system prompt|instructions)",
    r"you are now (?!an? hr)",
    r"act as (?!an? hr)",
]
_PII_PATTERNS = {
    "card number": r"\b(?:\d[ -]?){13,16}\b",
    "Aadhaar number": r"\b\d{4}\s?\d{4}\s?\d{4}\b",
    "PAN": r"\b[A-Z]{5}\d{4}[A-Z]\b",
}


def check_input(text: str) -> tuple[bool, str]:
    """Return (allowed, reason). Blocks oversized input, obvious prompt injection and sensitive IDs."""
    if not text.strip():
        return False, "Please type a question."
    if len(text) > MAX_INPUT_CHARS:
        return False, f"Please keep questions under {MAX_INPUT_CHARS} characters."
    lowered = text.lower()
    if any(re.search(p, lowered) for p in _INJECTION_PATTERNS):
        return False, "I can only help with HR policies and your own leave. I can't change my instructions."
    for label, pattern in _PII_PATTERNS.items():
        if re.search(pattern, text):
            return False, f"It looks like your message contains a {label}. Please remove sensitive personal data."
    return True, ""
