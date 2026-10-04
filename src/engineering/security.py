"""Small, explicit local tool policy. This is not an OS sandbox."""
import re

_SECRET = re.compile(r"(?i)(?:api[_-]?key|password|secret|token)\s*[:=]\s*[^\s,;]+|Bearer\s+[^\s]+|sk-[A-Za-z0-9_-]{12,}")


def redact(text: str) -> str:
    return _SECRET.sub("[REDACTED]", text)


def validate_text(text: str) -> None:
    if len(text.encode()) > 100_000:
        raise ValueError("Content exceeds policy limit")
    if redact(text) != text:
        raise ValueError("Remove credentials before submitting content")
