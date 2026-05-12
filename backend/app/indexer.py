"""Magezi PDF + JSON ingestion pipeline.

Extracts text from NCDC syllabus PDFs, chunks it into passages,
and loads alongside the structured JSON syllabus data into the
keyword-searchable index.

Usage:
    python -m app.indexer                    # Ingest all PDFs + JSON
    python -m app.indexer --pdfs-only        # Only PDFs
    python -m app.indexer --json-only        # Only JSON
"""

from __future__ import annotations

import json
import logging
import re
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_DOCS_DIR = _PROJECT_ROOT / "docs"
_SYLLABUS_DIR = _PROJECT_ROOT / "knowledge-base" / "syllabus"
_OUTPUT_DIR = _PROJECT_ROOT / "knowledge-base" / "extracted"

# Map PDF filenames to subject IDs
PDF_SUBJECT_MAP = {
    "Physics.pdf": "physics",
    "CHEMISTRY.pdf": "chemistry",
    "Biology.pdf": "biology",
    "PRINCIPAL MATHS.pdf": "mathematics",
}

# Pages to skip (cover, TOC, foreword, acknowledgements)
SKIP_PAGES_BEFORE = 10  # Skip first N pages of front matter


def extract_pdf_text(pdf_path: Path) -> list[dict[str, str]]:
    """Extract text from a PDF, returning a list of page-level passages."""
    try:
        import fitz  # PyMuPDF
    except ImportError:
        logger.error("PyMuPDF not installed: pip install pymupdf")
        return []

    doc = fitz.open(str(pdf_path))
    pages: list[dict[str, str]] = []

    for page_num in range(len(doc)):
        if page_num < SKIP_PAGES_BEFORE:
            continue

        page = doc[page_num]
        text = page.get_text("text").strip()

        # Skip nearly empty pages (headers/footers only)
        if len(text) < 50:
            continue

        # Clean up common PDF artifacts
        text = re.sub(r'\n{3,}', '\n\n', text)  # Collapse multiple blank lines
        text = re.sub(r'www\.ncdc\.go\.ug', '', text)  # Remove footer URLs
        text = re.sub(r'ADVANCED SECONDARY CURRICULUM\s*NCDC', '', text)  # Headers
        text = text.strip()

        if text:
            pages.append({
                "text": text,
                "page": str(page_num + 1),
                "source": pdf_path.name,
            })

    doc.close()
    logger.info("Extracted %d pages from %s", len(pages), pdf_path.name)
    return pages


def chunk_pages(
    pages: list[dict[str, str]],
    subject: str,
    chunk_size: int = 800,
    overlap: int = 100,
) -> list[dict[str, str]]:
    """Split page-level text into smaller overlapping chunks for better retrieval."""
    chunks: list[dict[str, str]] = []

    for page_data in pages:
        text = page_data["text"]
        page = page_data["page"]
        source = page_data["source"]

        # If text is short enough, keep as single chunk
        if len(text) <= chunk_size:
            chunks.append({
                "text": text,
                "page": page,
                "source": f"NCDC {subject.title()} Syllabus 2025 (PDF)",
                "subject": subject,
                "doc_type": "pdf",
                "chunk_id": f"{subject}-p{page}-0",
            })
            continue

        # Split into chunks with overlap
        words = text.split()
        i = 0
        chunk_idx = 0
        while i < len(words):
            chunk_words = words[i:i + chunk_size // 5]  # ~5 chars per word avg
            chunk_text = " ".join(chunk_words)

            if len(chunk_text.strip()) > 30:
                chunks.append({
                    "text": chunk_text.strip(),
                    "page": page,
                    "source": f"NCDC {subject.title()} Syllabus 2025 (PDF)",
                    "subject": subject,
                    "doc_type": "pdf",
                    "chunk_id": f"{subject}-p{page}-{chunk_idx}",
                })
                chunk_idx += 1

            # Advance with overlap
            step = max(1, len(chunk_words) - overlap // 5)
            i += step

    logger.info("Chunked into %d passages for %s", len(chunks), subject)
    return chunks


def ingest_pdfs() -> list[dict[str, str]]:
    """Extract and chunk all NCDC syllabus PDFs."""
    all_chunks: list[dict[str, str]] = []

    for pdf_name, subject in PDF_SUBJECT_MAP.items():
        pdf_path = _DOCS_DIR / pdf_name
        if not pdf_path.exists():
            logger.warning("PDF not found: %s", pdf_path)
            continue

        pages = extract_pdf_text(pdf_path)
        chunks = chunk_pages(pages, subject)
        all_chunks.extend(chunks)

    return all_chunks


def ingest_json() -> list[dict[str, str]]:
    """Load structured JSON syllabus files."""
    entries: list[dict[str, str]] = []

    if not _SYLLABUS_DIR.is_dir():
        return entries

    for json_path in sorted(_SYLLABUS_DIR.glob("*.json")):
        subject = json_path.stem
        try:
            with open(json_path, encoding="utf-8") as fh:
                data = json.load(fh)

            for topic_group in data.get("topics", []):
                group_name = topic_group.get("name", "")
                inner_topics = topic_group.get("topics", [])
                if not inner_topics and topic_group.get("subtopics"):
                    inner_topics = [topic_group]

                for topic in inner_topics:
                    topic_name = topic.get("name", "")
                    for subtopic in topic.get("subtopics", []):
                        text = (
                            f"Subject: {subject.title()}\n"
                            f"Topic: {group_name} > {topic_name}\n"
                            f"Subtopic: {subtopic.get('name', '')}\n"
                            f"Content: {subtopic.get('content', '')}\n"
                            f"Competences: {', '.join(subtopic.get('competences', []))}"
                        )
                        entries.append({
                            "text": text,
                            "source": f"NCDC {subject.title()} Syllabus 2025",
                            "subject": subject,
                            "topic": f"{group_name} > {topic_name}",
                            "section": subtopic.get("name", ""),
                            "doc_type": "syllabus",
                        })
        except Exception:
            logger.exception("Failed to load %s", json_path)

    logger.info("Loaded %d JSON entries", len(entries))
    return entries


def save_extracted(chunks: list[dict[str, str]]) -> None:
    """Save extracted passages to JSON for inspection."""
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = _OUTPUT_DIR / "all_passages.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(chunks, f, indent=2, ensure_ascii=False)
    logger.info("Saved %d passages to %s", len(chunks), out_path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    mode = sys.argv[1] if len(sys.argv) > 1 else "--all"

    all_passages: list[dict[str, str]] = []

    if mode in ("--all", "--pdfs-only"):
        pdf_chunks = ingest_pdfs()
        all_passages.extend(pdf_chunks)
        print(f"  PDFs: {len(pdf_chunks)} passages from {len(PDF_SUBJECT_MAP)} files")

    if mode in ("--all", "--json-only"):
        json_entries = ingest_json()
        all_passages.extend(json_entries)
        print(f"  JSON: {len(json_entries)} passages from syllabus files")

    save_extracted(all_passages)
    print(f"\n  TOTAL: {len(all_passages)} passages saved to knowledge-base/extracted/")


if __name__ == "__main__":
    main()
