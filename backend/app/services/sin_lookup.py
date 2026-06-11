import re

_HIDDEN_SIN_CHARS_RE = re.compile("[\u200B-\u200D\uFEFF]")


def normalize_sin(value: object) -> str:
    without_hidden_chars = _HIDDEN_SIN_CHARS_RE.sub("", str(value or ""))
    return re.sub(r"\s+", "", without_hidden_chars).upper()
