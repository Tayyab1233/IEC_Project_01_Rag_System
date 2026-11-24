"""Document extraction pipeline for PDF, DOCX, TXT, and Markdown.

Enforces:
- PyMuPDF page-by-page extraction with Markdown tables and repeated running header/footer stripping.
- 400 Bad Request if total extracted text from PDF is < 20 characters (scanned PDFs not supported).
- python-docx hierarchical section heading tracking (H1/H2/H3) and table conversion in document order.
- TXT / MD direct UTF-8 extraction with section metadata.
"""

import io
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import List, Optional

import docx
import fitz  # PyMuPDF
from fastapi import HTTPException, status


@dataclass
class ExtractedSection:
    """A discrete extracted content section associated with a page or heading."""

    content: str
    page_number: Optional[int] = None
    section_heading: Optional[str] = None
    page_or_section: str = "General"


@dataclass
class ExtractedDocument:
    """Container for all extracted sections of a document."""

    filename: str
    mime_type: str
    total_pages: int
    sections: List[ExtractedSection] = field(default_factory=list)
    total_chars: int = 0


class DocumentExtractor:
    """Unified document text and table extractor."""

    @staticmethod
    def extract(filename: str, content: bytes, mime_type: str) -> ExtractedDocument:
        """Extract content from file bytes based on mime type or filename.

        Args:
            filename: Original file name.
            content: Raw file bytes.
            mime_type: Validated MIME type.

        Returns:
            ExtractedDocument containing all extracted sections.

        Raises:
            HTTPException(400): If document has insufficient extractable text.
        """
        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            return DocumentExtractor._extract_pdf(filename, content)
        elif (
            mime_type
            == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            or filename.lower().endswith(".docx")
        ):
            return DocumentExtractor._extract_docx(filename, content)
        elif mime_type == "text/markdown" or filename.lower().endswith(".md"):
            return DocumentExtractor._extract_markdown(filename, content)
        elif mime_type == "text/plain" or filename.lower().endswith(".txt"):
            return DocumentExtractor._extract_text(filename, content)
        else:
            raise HTTPException(
                status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                detail=f"Unsupported media type for extraction: {mime_type}",
            )

    # -------------------------------------------------------------------------
    # PDF Extraction (PyMuPDF + find_tables + header/footer stripping)
    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_pdf(filename: str, content: bytes) -> ExtractedDocument:
        """Extract text and markdown tables from PDF page-by-page."""
        try:
            doc = fitz.open(stream=content, filetype="pdf")
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse PDF document: {exc}",
            )

        total_pages = doc.page_count
        raw_pages_lines: List[List[str]] = []

        # First pass: collect raw lines per page to identify repeated running headers/footers
        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_text = page.get_text("text") or ""
            lines = [line.strip() for line in page_text.splitlines() if line.strip()]
            raw_pages_lines.append(lines)

        # Detect repeated headers and footers (>60% of pages when total_pages > 2)
        repeated_lines = set()
        if total_pages > 2:
            candidate_counter = Counter()
            for lines in raw_pages_lines:
                if not lines:
                    continue
                # Top 2 lines (candidate headers)
                for line in lines[:2]:
                    # Ignore pure page numbers (e.g. "1", "Page 1")
                    norm = re.sub(r"\bpage\s*\d+\b|\b\d+\b", "", line, flags=re.I).strip()
                    if norm:
                        candidate_counter[norm] += 1
                # Bottom 2 lines (candidate footers)
                for line in lines[-2:]:
                    norm = re.sub(r"\bpage\s*\d+\b|\b\d+\b", "", line, flags=re.I).strip()
                    if norm:
                        candidate_counter[norm] += 1

            threshold = 0.60 * total_pages
            for norm_line, count in candidate_counter.items():
                if count >= threshold:
                    repeated_lines.add(norm_line)

        sections: List[ExtractedSection] = []
        total_extracted_chars = 0

        # Second pass: extract page text (minus repeated headers/footers) + Markdown tables
        for page_idx in range(total_pages):
            page = doc[page_idx]
            page_number = page_idx + 1
            lines = raw_pages_lines[page_idx]

            # Filter out lines matching repeated header/footer norms
            filtered_lines = []
            for line in lines:
                norm = re.sub(r"\bpage\s*\d+\b|\b\d+\b", "", line, flags=re.I).strip()
                if norm and norm in repeated_lines:
                    continue
                filtered_lines.append(line)

            page_body_text = "\n".join(filtered_lines)

            # Detect tables and convert to Markdown
            table_markdown_blocks = []
            try:
                tables = page.find_tables()
                if tables and tables.tables:
                    for tab in tables.tables:
                        tab_md = tab.to_markdown()
                        if tab_md and tab_md.strip():
                            table_markdown_blocks.append(tab_md.strip())
            except Exception:
                pass  # Fallback to plain text if table parser encounters an anomaly

            full_page_content_parts = []
            if page_body_text:
                full_page_content_parts.append(page_body_text)
            if table_markdown_blocks:
                full_page_content_parts.append("\n\n".join(table_markdown_blocks))

            page_content = "\n\n".join(full_page_content_parts).strip()
            total_extracted_chars += len(page_content)

            if page_content:
                sections.append(
                    ExtractedSection(
                        content=page_content,
                        page_number=page_number,
                        section_heading=None,
                        page_or_section=f"Page {page_number}",
                    )
                )

        # Scanned PDF check: reject if total extracted text is under 20 characters
        if total_extracted_chars < 20:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No extractable text found; scanned PDFs are not supported",
            )

        return ExtractedDocument(
            filename=filename,
            mime_type="application/pdf",
            total_pages=total_pages,
            sections=sections,
            total_chars=total_extracted_chars,
        )

    # -------------------------------------------------------------------------
    # DOCX Extraction (Heading tracking & table conversion in document order)
    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_docx(filename: str, content: bytes) -> ExtractedDocument:
        """Extract text and tables from DOCX preserving document order and heading context."""
        try:
            doc = docx.Document(io.BytesIO(content))
        except Exception as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to parse DOCX document: {exc}",
            )

        current_heading = "Introduction"
        sections: List[ExtractedSection] = []
        current_section_lines: List[str] = []
        total_chars = 0

        def flush_section():
            nonlocal current_section_lines, current_heading, total_chars
            if current_section_lines:
                sec_text = "\n".join(current_section_lines).strip()
                if sec_text:
                    sections.append(
                        ExtractedSection(
                            content=sec_text,
                            page_number=None,
                            section_heading=current_heading,
                            page_or_section=current_heading,
                        )
                    )
                    total_chars += len(sec_text)
                current_section_lines = []

        # Iterate over child elements in document body order
        for child in doc.element.body:
            tag = child.tag
            if tag.endswith("p"):  # Paragraph
                p = docx.text.paragraph.Paragraph(child, doc)
                text = p.text.strip()
                if not text:
                    continue

                style_name = (p.style.name or "") if p.style else ""
                # Check if paragraph is a heading (Heading 1/2/3)
                if re.match(r"^heading\s+[1-3]", style_name, flags=re.I) or style_name.startswith("Heading"):
                    flush_section()
                    current_heading = text
                    current_section_lines.append(f"## {text}")
                else:
                    current_section_lines.append(text)

            elif tag.endswith("tbl"):  # Table
                table = docx.table.Table(child, doc)
                # Convert DOCX table to Markdown
                md_rows = []
                for row_idx, row in enumerate(table.rows):
                    cell_texts = [re.sub(r"\s+", " ", cell.text.strip()) for cell in row.cells]
                    md_rows.append("| " + " | ".join(cell_texts) + " |")
                    if row_idx == 0:
                        # Add markdown header separator
                        md_rows.append("| " + " | ".join(["---"] * len(cell_texts)) + " |")

                if md_rows:
                    current_section_lines.append("\n" + "\n".join(md_rows) + "\n")

        flush_section()

        if total_chars < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No extractable text found in DOCX document",
            )

        return ExtractedDocument(
            filename=filename,
            mime_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            total_pages=1,
            sections=sections,
            total_chars=total_chars,
        )

    # -------------------------------------------------------------------------
    # Markdown Extraction (Tracking H1/H2/H3 headers)
    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_markdown(filename: str, content: bytes) -> ExtractedDocument:
        """Extract text from Markdown tracking active section headings."""
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Markdown file contains invalid UTF-8: {exc}",
            )

        lines = text.splitlines()
        current_heading = "Overview"
        current_section_lines: List[str] = []
        sections: List[ExtractedSection] = []
        total_chars = 0

        def flush_section():
            nonlocal current_section_lines, current_heading, total_chars
            if current_section_lines:
                sec_text = "\n".join(current_section_lines).strip()
                if sec_text:
                    sections.append(
                        ExtractedSection(
                            content=sec_text,
                            page_number=None,
                            section_heading=current_heading,
                            page_or_section=current_heading,
                        )
                    )
                    total_chars += len(sec_text)
                current_section_lines = []

        for line in lines:
            header_match = re.match(r"^#{1,3}\s+(.+)$", line.strip())
            if header_match:
                flush_section()
                current_heading = header_match.group(1).strip()
                current_section_lines.append(line)
            else:
                current_section_lines.append(line)

        flush_section()

        if total_chars < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Markdown file contains no text.",
            )

        return ExtractedDocument(
            filename=filename,
            mime_type="text/markdown",
            total_pages=1,
            sections=sections,
            total_chars=total_chars,
        )

    # -------------------------------------------------------------------------
    # TXT Extraction (Direct UTF-8 stream with line chunks)
    # -------------------------------------------------------------------------
    @staticmethod
    def _extract_text(filename: str, content: bytes) -> ExtractedDocument:
        """Extract raw UTF-8 text from TXT file."""
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Text file contains invalid UTF-8: {exc}",
            )

        cleaned_text = text.strip()
        if not cleaned_text:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Text file contains no text.",
            )

        sections = [
            ExtractedSection(
                content=cleaned_text,
                page_number=1,
                section_heading=None,
                page_or_section="Lines 1-end",
            )
        ]

        return ExtractedDocument(
            filename=filename,
            mime_type="text/plain",
            total_pages=1,
            sections=sections,
            total_chars=len(cleaned_text),
        )
