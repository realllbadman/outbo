import re
from typing import Optional

EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
ZIP_RE = re.compile(r"\d{5}(-\d{4})?")


def parse_int(value: Optional[str]) -> Optional[int]:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def one_line(value: str, limit: int) -> str:
    """Collapse whitespace (so newlines can't reach email headers) and cap the length."""
    return " ".join(value.split())[:limit]
