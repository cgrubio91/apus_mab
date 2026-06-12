"""
Post-processing cleaners for extracted APU data.
"""

import re
import unicodedata
from datetime import datetime


def format_latin_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s or s in ("–", "—", "-", "", "N/A", "n/a"):
        return None
    s = s.replace(" ", "").replace("$", "").replace("COP", "").replace("USD", "")
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        pass
    match = re.search(r"\d+[\.]?\d*", s.replace(",", "."))
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def format_date(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d")
    s = str(value).strip()
    if not s or s in ("–", "—", "-", "", "N/A", "n/a"):
        return None
    for fmt in [
        "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%m-%d-%Y",
        "%Y/%m/%d", "%d.%m.%Y", "%Y.%m.%d",
        "%d %b %Y", "%d %B %Y", "%b %d %Y",
    ]:
        try:
            return datetime.strptime(s, fmt).strftime("%Y-%m-%d")
        except (ValueError, TypeError):
            continue
    return s


def clean_numeric_value(value) -> float | None:
    return format_latin_number(value)


def clean_text_field(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    s = unicodedata.normalize("NFKC", s)
    s = re.sub(r"\s+", " ", s)
    return s if s else None
