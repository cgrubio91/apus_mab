"""
📄 PDF Parser Module
Extracts text from PDF files locally and encodes PDFs to base64 for Gemini direct multimodal processing.
"""

import os
import base64
from pypdf import PdfReader

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
