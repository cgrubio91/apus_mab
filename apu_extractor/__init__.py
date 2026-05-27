"""
📦 APU Extractor Package
Exposes core routines for parsing documents, extracting structured APU data using Gemini AI, 
formatting output for Google Sheets, and saving/loading data from the database.
"""

from apu_extractor.pdf_parser import extract_text_from_pdf, get_pdf_base64, extract_text_from_pdf_batched, split_pdf_to_base64_batches
from apu_extractor.excel_parser import extract_text_from_excel, excel_to_dataframe_dict, extract_text_from_excel_batched
from apu_extractor.gemini_extractor import (
    extract_apus_from_text,
    extract_apus_from_pdf_multimodal,
    extract_apus_from_excel,
    extract_apus_from_pdf_batched,
    post_process_extracted_data,
    generate_copy_paste_table,
    format_latin_number,
    format_date
)
from apu_extractor.db_service import (
    insert_apus_batch,
    insert_apus_stream,
    get_unique_projects,
    get_apus,
    get_dashboard_stats,
    delete_project_apus
)

__all__ = [
    'extract_text_from_pdf',
    'get_pdf_base64',
    'extract_text_from_pdf_batched',
    'split_pdf_to_base64_batches',
    'extract_text_from_excel',
    'excel_to_dataframe_dict',
    'extract_text_from_excel_batched',
    'extract_apus_from_text',
    'extract_apus_from_pdf_multimodal',
    'extract_apus_from_pdf_batched',
    'extract_apus_from_excel',
    'post_process_extracted_data',
    'generate_copy_paste_table',
    'format_latin_number',
    'format_date',
    'insert_apus_batch',
    'insert_apus_stream',
    'get_unique_projects',
    'get_apus',
    'get_dashboard_stats',
    'delete_project_apus'
]
