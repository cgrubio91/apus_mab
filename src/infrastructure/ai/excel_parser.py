"""
Infrastructure: Excel Parser
Extracts text from Excel files for AI consumption.
"""

import logging
import pandas as pd

log = logging.getLogger("mapus.extractor.excel")


def extract_text_from_excel(excel_path: str) -> str:
    df_dict = excel_to_dataframe_dict(excel_path)
    fragments = []
    for sheet_name, df in df_dict.items():
        fragments.append(f"=== Hoja: {sheet_name} ===")
        fragments.append(df.to_string(index=False))
    return "\n\n".join(fragments)


def excel_to_dataframe_dict(excel_path: str) -> dict[str, pd.DataFrame]:
    xls = pd.ExcelFile(excel_path)
    df_dict = {}
    for sheet_name in xls.sheet_names:
        df = xls.parse(sheet_name, dtype=str)
        df = df.dropna(how="all").fillna("")
        df_dict[sheet_name] = df
    return df_dict


def extract_text_from_excel_batched(excel_path: str, max_chars: int = 50000) -> list[str]:
    text = extract_text_from_excel(excel_path)
    batches = []
    for i in range(0, len(text), max_chars):
        batches.append(text[i: i + max_chars])
    return batches if batches else [text]
