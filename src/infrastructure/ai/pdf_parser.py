"""
Infrastructure: PDF Parser
Extracts text from PDF files with batching for large documents.
"""

import base64
import logging
import os
import tempfile
from typing import Optional

log = logging.getLogger("mapus.extractor.pdf")


def extract_text_from_pdf(pdf_path: str) -> str:
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)
    return "\n".join(pages_text)


def get_pdf_base64(pdf_path: str) -> str:
    with open(pdf_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def split_pdf_to_base64_batches(pdf_path: str, batch_size: int = 15) -> list[dict]:
    from pypdf import PdfReader
    reader = PdfReader(pdf_path)
    total_pages = len(reader.pages)
    batches = []

    for start in range(0, total_pages, batch_size):
        end = min(start + batch_size, total_pages)
        with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
            from pypdf import PdfWriter
            writer = PdfWriter()
            for i in range(start, end):
                writer.add_page(reader.pages[i])
            writer.write(tmp)
            tmp_path = tmp.name

        with open(tmp_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode("utf-8")

        os.unlink(tmp_path)

        pages_text = "\n".join(
            reader.pages[i].extract_text() or "" for i in range(start, end)
        )

        batches.append({
            "index": start // batch_size,
            "pages": f"{start + 1}-{end}",
            "text": pages_text,
            "base64": b64,
        })

    return batches


def extract_text_from_pdf_batched(pdf_path: str, batch_size: int = 15) -> list[str]:
    batches = split_pdf_to_base64_batches(pdf_path, batch_size)
    return [b["text"] for b in batches]
