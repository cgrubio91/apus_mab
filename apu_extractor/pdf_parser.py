"""
📄 PDF Parser Module
Extracts text from PDF files locally and encodes PDFs to base64 for Gemini direct multimodal processing.
Optimized for high resilience against corrupted pages, scans, and encryption constraints.
"""

import io
import os
import base64
import logging
from typing import Generator, Tuple
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

log = logging.getLogger("mapus.extractor.pdf")

# Tamaño de lote regulable de páginas para optimizar la ventana de contexto de la IA
PDF_BATCH_SIZE = 5


def extract_text_from_pdf_batched(pdf_path: str, batch_size: int = PDF_BATCH_SIZE) -> Generator[Tuple[str, str], None, None]:
    """
    Extracts text from a PDF file page by page, yielding batches of pages as text chunks.
    CORRECCIÓN: Validación dura del batch_size para evitar bucles o comportamientos rotos en range().
    """
    if batch_size <= 0:
        raise ValueError("El parámetro 'batch_size' debe ser estrictamente mayor a cero.")

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
    except PdfReadError as pre:
        log.error("Failed to read PDF due to corruption or encryption: %s", pre)
        raise RuntimeError(f"El archivo PDF está corrupto o protegido por contraseña: {pre}")
    except Exception as e:
        log.exception("Unexpected error opening PDF metadata")
        raise RuntimeError(f"Fallo crítico al abrir el archivo PDF: {e}")

    for start in range(0, total_pages, batch_size):
        end = min(start + batch_size, total_pages)
        batch_text = []
        
        for i in range(start, end):
            try:
                page_text = reader.pages[i].extract_text()
                if page_text and page_text.strip():
                    batch_text.append(f"--- PÁGINA {i + 1} ---\n{page_text}")
            except Exception as page_err:
                log.warning("No se pudo leer la capa de texto de la página %d en %s: %s", i + 1, pdf_path, page_err)
                continue
        
        if batch_text:
            label = f"páginas {start + 1}-{end} de {total_pages}"
            yield label, "\n\n".join(batch_text)


def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts all text content from a PDF file.
    Incluye telemetría defensiva para alertar de forma temprana si el PDF es escaneado (sin texto).
    """
    text_content = []
    try:
        for _, text_chunk in extract_text_from_pdf_batched(pdf_path, batch_size=PDF_BATCH_SIZE):
            if text_chunk.strip():
                text_content.append(text_chunk)
                
        final_text = "\n\n".join(text_content)
        
        if not final_text.strip():
            log.warning("⚠️ PDF sin texto extraíble detectado (posible documento escaneado/imagen): %s", pdf_path)
            
        return final_text
    except Exception as e:
        log.exception("Critical error aggregating full PDF text")
        raise RuntimeError(f"Fallo general en la agregación de texto del PDF: {e}")


def split_pdf_to_base64_batches(pdf_path: str, batch_size: int = PDF_BATCH_SIZE) -> Generator[Tuple[str, str], None, None]:
    """
    Splits a PDF into page batches (as base64-encoded PDFs) for multimodal processing.
    CORRECCIÓN: Validación dura del batch_size para evitar bucles o comportamientos rotos en range().
    """
    if batch_size <= 0:
        raise ValueError("El parámetro 'batch_size' debe ser estrictamente mayor a cero.")

    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

    try:
        reader = PdfReader(pdf_path)
        total_pages = len(reader.pages)
    except Exception as e:
        log.exception("Failed to initialize PDF split reader")
        raise RuntimeError(f"Error abriendo PDF para segmentación multimodal: {e}")

    for start in range(0, total_pages, batch_size):
        end = min(start + batch_size, total_pages)
        writer = PdfWriter()
        buf = io.BytesIO()
        
        try:
            for i in range(start, end):
                writer.add_page(reader.pages[i])

            writer.write(buf)
            buf.seek(0)
            encoded = base64.b64encode(buf.read()).decode("utf-8")
            
            label = f"páginas {start + 1}-{end} de {total_pages}"
            yield label, encoded
            
        except Exception as batch_err:
            log.error("Fallo al segmentar lote multimodal %d-%d: %s", start+1, end, batch_err)
            continue
        finally:
            buf.close()
            if hasattr(writer, "close"):
                writer.close()


def get_pdf_base64(pdf_path: str) -> str:
    """
    Reads a PDF file and returns its content as a single base64 encoded string.
    Useful for direct full-document multimodal processing.
    """
    # CORRECCIÓN: Validación de existencia en primer lugar para evitar excepciones crudas de getsize()
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"PDF file not found at: {pdf_path}")

    if os.getenv("ENV", "").lower() != "production":
        file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
        if file_size_mb > 50:
            log.warning("Archivo PDF detectado de gran tamaño (%.2f MB). Riesgo de sobrecarga de heap.", file_size_mb)
        
    try:
        with open(pdf_path, "rb") as pdf_file:
            return base64.b64encode(pdf_file.read()).decode("utf-8")
    except Exception as e:
        log.error("Failed to encode complete PDF to base64: %s", e, exc_info=True)
        raise RuntimeError(f"Error crítico codificando el flujo binario del PDF: {e}")


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    
    if len(sys.argv) > 1:
        test_path = sys.argv[1]
        log.info("📄 Testing memory-safe PDF extraction on: %s", test_path)
        try:
            txt = extract_text_from_pdf(test_path)
            log.info("✅ Success. Extracted %d characters.", len(txt))
            print("\nPreview of first 300 characters:")
            print("-" * 40)
            print(txt[:300])
            print("-" * 40)
        except Exception as err:
            log.error("Test pipeline execution failed: %s", err)
    else:
        print("💡 Usage: python pdf_parser.py <path_to_pdf>")