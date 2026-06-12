import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from apu_extractor.gemini_extractor import (
    clean_numeric_value,
    format_latin_number,
    format_date,
    clean_text_field,
)
from decimal import Decimal


def test_clean_numeric_none():
    assert clean_numeric_value(None) is None


def test_clean_numeric_empty_string():
    assert clean_numeric_value("") is None


def test_clean_numeric_dash():
    assert clean_numeric_value("–") is None


def test_clean_numeric_with_dollar():
    result = clean_numeric_value("$45,000.5")
    assert result == Decimal("45000.5")


def test_clean_numeric_with_percent():
    result = clean_numeric_value("12.5%")
    assert result == Decimal("12.5")


def test_clean_numeric_latin_format():
    result = clean_numeric_value("12.500,50")
    assert result == Decimal("12500.50")


def test_clean_numeric_integer():
    result = clean_numeric_value(1234567)
    assert isinstance(result, Decimal)


def test_format_latin_none():
    assert format_latin_number(None) == "–"


def test_format_latin_integer():
    assert format_latin_number(1234567) == "1.234.567"


def test_format_latin_decimal():
    result = format_latin_number(Decimal("0.25"))
    assert result == "0,25"


def test_format_date_none():
    assert format_date(None) == "–"


def test_format_date_iso():
    assert format_date("2026-05-25") == "2026-05-25"


def test_format_date_dmy():
    assert format_date("25/05/2026") == "2026-05-25"


def test_format_date_mdy():
    assert format_date("05-25-2026") == "2026-05-25"


def test_clean_text_field_none():
    assert clean_text_field(None) == "–"


def test_clean_text_field_whitespace():
    assert clean_text_field("  hello  ") == "hello"


def test_clean_text_field_multi_line():
    assert clean_text_field("hello\nworld") == "hello world"
