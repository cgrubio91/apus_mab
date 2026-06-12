"""
📦 APU Extractor Package — Compatibility Wrapper
All logic now lives in src/infrastructure/ai/ and src/infrastructure/database/repositories/
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from src.infrastructure.ai.pdf_parser import (
    extract_text_from_pdf,
    get_pdf_base64,
    extract_text_from_pdf_batched,
    split_pdf_to_base64_batches,
)
from src.infrastructure.ai.excel_parser import (
    extract_text_from_excel,
    excel_to_dataframe_dict,
    extract_text_from_excel_batched,
)
from src.infrastructure.ai.gemini_extractor import (
    extract_apus_from_text,
    extract_apus_from_pdf_multimodal,
    extract_apus_from_excel,
    extract_apus_from_pdf_batched,
    post_process_extracted_data,
    generate_copy_paste_table,
)
from src.infrastructure.ai.gemini_cleaners import (
    format_latin_number,
    format_date,
    clean_numeric_value,
    clean_text_field,
)
from src.infrastructure.ai.gemini_prompts import (
    get_extraction_prompt,
    get_response_schema,
)
from src.infrastructure.database.repositories.apu_repository import (
    insert_apus_batch,
    insert_apus_stream,
    get_unique_projects,
    get_apus,
    get_dashboard_stats,
    delete_project_apus,
)

__all__ = [
    'extract_text_from_pdf', 'get_pdf_base64', 'extract_text_from_pdf_batched',
    'split_pdf_to_base64_batches', 'extract_text_from_excel',
    'excel_to_dataframe_dict', 'extract_text_from_excel_batched',
    'extract_apus_from_text', 'extract_apus_from_pdf_multimodal',
    'extract_apus_from_pdf_batched', 'extract_apus_from_excel',
    'post_process_extracted_data', 'generate_copy_paste_table',
    'format_latin_number', 'format_date', 'clean_numeric_value',
    'clean_text_field', 'get_extraction_prompt', 'get_response_schema',
    'insert_apus_batch', 'insert_apus_stream', 'get_unique_projects',
    'get_apus', 'get_dashboard_stats', 'delete_project_apus',
]
