"""
📄 PDF Parser Module
Extracts text from PDF files locally and encodes PDFs to base64 for Gemini direct multimodal processing.
"""

import io
import os
import base64
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

PDF_BATCH_SIZE = 5  # pages per batch


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts all text content from a PDF file.
    
    Args:
        pdf_path (str): Absolute path to the PDF file.
        
    Returns:
        str: Extracted text from the PDF.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")
        
    try:
        reader = PdfReader(pdf_path)
        text_content = []
        
        for i, page in enumerate(reader.pages):
            page_text = page.extract_text()
            if page_text:
                text_content.append(f"--- PÁGINA {i+1} ---\n{page_text}")
                
        return "\n\n".join(text_content)
    except Exception as e:
        raise Exception(f"Failed to extract text from PDF: {e}")


def extract_text_from_pdf_batched(pdf_path: str):
    """
    Extracts text from a PDF file page by page, yielding batches of pages
    as text chunks. This prevents overwhelming the AI with the full document.

    Yields:
        tuple[str, str]: (batch_label, text_chunk)
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
        all_text = []

        for i, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            all_text.append(f"--- PÁGINA {i+1} ---\n{page_text}")

            if (i + 1) % PDF_BATCH_SIZE == 0 or (i + 1) == total_pages:
                start_page = i + 1 - (len(all_text) - 1)
                label = f"páginas {start_page}-{i+1} de {total_pages}"
                yield label, "\n\n".join(all_text)
                all_text = []

    except PdfReadError as e:
        raise Exception(f"Failed to read PDF (corrupted or encrypted): {e}")
    except Exception as e:
        raise Exception(f"Failed to extract text from PDF: {e}")


def split_pdf_to_base64_batches(pdf_path: str):
    """
    Splits a PDF into page batches (as base64-encoded PDFs) for multimodal processing.

    Yields:
        tuple[str, str]: (batch_label, base64_pdf_data)
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)

        for start in range(0, total_pages, PDF_BATCH_SIZE):
            end = min(start + PDF_BATCH_SIZE, total_pages)
            writer = PdfWriter()
            for i in range(start, end):
                writer.add_page(reader.pages[i])

            buf = io.BytesIO()
            writer.write(buf)
            buf.seek(0)
            encoded = base64.b64encode(buf.read()).decode("utf-8")
            label = f"páginas {start+1}-{end} de {total_pages}"
            yield label, encoded

    except PdfReadError as e:
        raise Exception(f"Failed to split PDF (corrupted or encrypted): {e}")
    except Exception as e:
        raise Exception(f"Failed to split PDF: {e}")


def get_pdf_base64(pdf_path: str) -> str:
    """
    Reads a PDF file and returns its content as a base64 encoded string.
    Useful for direct multimodal processing with Gemini API.
    
    Args:
        pdf_path (str): Absolute path to the PDF file.
        
    Returns:
        str: Base64 encoded string of the PDF content.
    """
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")
        
    try:
        with open(pdf_path, "rb") as pdf_file:
            encoded_string = base64.b64encode(pdf_file.read()).decode("utf-8")
        return encoded_string
    except Exception as e:
        raise Exception(f"Failed to encode PDF to base64: {e}")


if __name__ == "__main__":
    # Test script if executed directly
    import sys
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        print(f"📄 Testing PDF extraction on: {test_path}")
        try:
            txt = extract_text_from_pdf(test_path)
            print(f"✅ Success. Extracted {len(txt)} chars.")
            print("\nPreview of first 300 chars:")
            print("-" * 40)
            print(txt[:300])
            print("-" * 40)
        except Exception as err:
            print(f"❌ Error: {err}")
    else:
        print("💡 Usage: python pdf_parser.py <path_to_pdf>")
