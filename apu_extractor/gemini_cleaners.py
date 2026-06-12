import re
import logging
from decimal import Decimal, InvalidOperation
from datetime import datetime

log = logging.getLogger("mapus.extractor.cleaners")


def clean_numeric_value(value: str | int | float | Decimal | None) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    if isinstance(value, Decimal):
        return value

    val_str = str(value).strip().replace('$', '').replace('€', '').replace('%', '').replace(' ', '').replace(' ', '')
    if not val_str or val_str in ('–', '—', '-', 'NULL', 'null', 'N/A', 'n/a', 'None'):
        return None

    if re.match(r'^[\dOoIl.,\-]+$', val_str):
        ocr_map = {'O': '0', 'o': '0', 'l': '1', 'I': '1'}
        for bad, good in ocr_map.items():
            val_str = val_str.replace(bad, good)

    try:
        if ',' in val_str and '.' in val_str:
            if val_str.find(',') < val_str.find('.'):
                clean_str = val_str.replace(',', '')
            else:
                clean_str = val_str.replace('.', '').replace(',', '.')
        elif ',' in val_str:
            clean_str = val_str.replace(',', '.')
        elif '.' in val_str:
            if val_str.count('.') > 1:
                clean_str = val_str.replace('.', '')
            else:
                parts = val_str.split('.')
                if len(parts) == 2 and len(parts[1]) == 3 and parts[0].lstrip('-').isdigit():
                    clean_str = val_str.replace('.', '')
                else:
                    clean_str = val_str
        else:
            clean_str = val_str

        return Decimal(clean_str)
    except (ValueError, InvalidOperation):
        try:
            return Decimal(val_str)
        except (ValueError, InvalidOperation):
            log.warning("No se pudo parsear el valor numérico de la celda: %s", value)
            return None


def format_latin_number(value: str | int | float | Decimal | None) -> str:
    num = clean_numeric_value(value)
    if num is None:
        return "–"

    try:
        if num == num.to_integral_value():
            return f"{int(num):,}".replace(",", ".")
        else:
            s = format(num.normalize(), 'f').rstrip('0')

            if not s or s == '-' or s == '-0':
                s = '0'

            if s.endswith('.'):
                s = s[:-1]

            parts = s.split('.')
            int_part = int(parts[0])
            dec_part = parts[1] if len(parts) > 1 else ""

            formatted_int = f"{int_part:,}".replace(",", ".")
            return f"{formatted_int},{dec_part}" if dec_part else formatted_int
    except Exception:
        log.exception("Error de formateo numérico en format_latin_number")
        return "–"


def format_date(value: str | None) -> str:
    if not value:
        return "–"
    val_str = str(value).strip()
    if val_str in ('–', '—', '-', 'NULL', 'null', 'N/A', 'n/a', 'None', ''):
        return "–"

    try:
        datetime.strptime(val_str, '%Y-%m-%d')
        return val_str
    except ValueError:
        pass

    formats = ['%d/%m/%Y', '%m/%d/%Y', '%Y/%m/%d', '%d-%m-%Y', '%m-%d-%Y', '%Y%m%d']
    for fmt in formats:
        try:
            date_obj = datetime.strptime(val_str, fmt)
            return date_obj.strftime('%Y-%m-%d')
        except ValueError:
            continue

    match = re.search(r'(\d{4})[-/](\d{1,2})[-/](\d{1,2})', val_str)
    if match:
        return f"{match.group(1)}-{int(match.group(2)):02d}-{int(match.group(3)):02d}"

    match_reverse = re.search(r'(\d{1,2})[-/](\d{1,2})[-/](\d{4})', val_str)
    if match_reverse:
        return f"{match_reverse.group(3)}-{int(match_reverse.group(2)):02d}-{int(match_reverse.group(1)):02d}"

    return "–"


def clean_text_field(value: str | int | float | None) -> str:
    if value is None:
        return "–"
    val_str = str(value).strip()
    if not val_str or val_str in ('–', '—', '-', 'NULL', 'null', 'N/A', 'n/a', 'None'):
        return "–"
    return re.sub(r"\s+", " ", val_str)


def normalize_ai_response(result: list | dict | None) -> list[dict]:
    if isinstance(result, dict):
        return result.get("insumos", [])
    return result if isinstance(result, list) else []
