import re


def normalize_sin(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).upper()

