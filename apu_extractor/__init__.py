"""
📦 APU Extractor Package
Exposes core routines for parsing documents, extracting structured APU data using Gemini AI, 
formatting output for Google Sheets, and saving/loading data from the database.
"""

from apu_extractor.pdf_parser import extract_text_from_pdf, get_pdf_base64
from apu_extractor.excel_parser import extract_text_from_excel, excel_to_dataframe_dict
from apu_extractor.gemini_extractor import (
    extract_apus_from_text,
    extract_apus_from_pdf_multimodal,
    post_process_extracted_data,
    generate_copy_paste_table,
    format_latin_number,
    format_date
)
from apu_extractor.db_service import (
    insert_apus_batch,
    get_unique_projects,
    get_apus,
    delete_project_apus
)

__all__ = [
    'extract_text_from_pdf',
    'get_pdf_base64',
    'extract_text_from_excel',
    'excel_to_dataframe_dict',
    'extract_apus_from_text',
    'extract_apus_from_pdf_multimodal',
    'post_process_extracted_data',
    'generate_copy_paste_table',
    'format_latin_number',
    'format_date',
    'insert_apus_batch',
    'get_unique_projects',
    'get_apus',
    'delete_project_apus'
]
