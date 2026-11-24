"""Text chunking with pre-split standalone label merging and injection detection.

Enforces:
- Pre-split normalization pass merging short standalone label/badge lines (<40 chars
  directly above a heading, e.g. "Tactic 1") into that heading.
- Recursive text splitting (~450 tokens / ~1800 chars, ~60 tokens / ~240 chars overlap).
- Prepending '[File: {file_name} | Location: {page_or_section}]' to each chunk.
- Scanning chunks for embedded prompt-injection phrases (flagging has_injection_warning=True).
"""

import re
import uuid
from dataclasses import dataclass
from typing import List, Optional

from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.app.config import get_settings
from backend.app.ingestion.extractor import ExtractedDocument, ExtractedSection

# Suspicious prompt-injection phrases to flag in chunk metadata
INJECTION_PATTERNS = [
    re.compile(r"\b(ignore|disregard|forget)\s+(all\s+)?(previous|prior|above)\s+instructions\b", re.IGNORECASE),
    re.compile(r"\b(system\s+prompt|developer\s+mode|jailbreak|dan\s+mode)\b", re.IGNORECASE),
    re.compile(r"\byou\s+are\s+now\s+(an?\s+)?(unrestricted|developer|ai\s+assistant\s+without\s+rules)\b", re.IGNORECASE),
    re.compile(r"\b(bypass\s+safety|override\s+instructions|reveal\s+canary|exfiltrate)\b", re.IGNORECASE),
    re.compile(r"<\s*(system|instruction|admin)\s*>", re.IGNORECASE),
]


@dataclass
class ProcessedChunk:
    """Represents a chunk ready for vectorization and storage."""

    chunk_id: str
    chunk_index: int
    content: str  # Prepended content with file & location context
    raw_text: str  # Original text without prefix
    page_number: Optional[int]
    section_heading: Optional[str]
    page_or_section: str
    has_injection_warning: bool
    token_count: int


def merge_standalone_labels(text: str) -> str:
    """Pre-split normalization pass: Merge short standalone label/badge lines into headings.

    Detects short standalone badge/label lines (<40 chars, e.g. 'Tactic 1' or 'Section A')
    sitting directly above a heading line and merges them so labels are never stranded
    at the end of a previous chunk.

    Args:
        text: Raw text to normalize.

    Returns:
        Normalized text with standalone labels merged into subsequent headings.
    """
    lines = text.splitlines()
    merged_lines: List[str] = []
    i = 0
    total_lines = len(lines)

    # Heading patterns: Markdown heading (# ...), Heading 1/2/3, or All-Caps line
    heading_pattern = re.compile(
        r"^(#{1,6}\s+.+|heading\s+\d+:?.*|[A-Z0-9\s\-]{3,50}:)$", re.IGNORECASE
    )

    while i < total_lines:
        line = lines[i]
        stripped = line.strip()

        # Check if current line is a candidate short standalone badge/label:
        # - non-empty
        # - shorter than 40 chars
        # - does not end with sentence punctuation (. ? !)
        # - not already a markdown heading
        is_candidate_label = (
            0 < len(stripped) < 40
            and not stripped.endswith((".", "?", "!"))
            and not stripped.startswith("#")
        )

        if is_candidate_label and i + 1 < total_lines:
            # Look ahead to see if the next non-empty line is a heading
            next_idx = i + 1
            while next_idx < total_lines and not lines[next_idx].strip():
                next_idx += 1

            if next_idx < total_lines:
                next_stripped = lines[next_idx].strip()
                if heading_pattern.match(next_stripped) or next_stripped.startswith("#"):
                    # Merge label into the heading line
                    merged_heading = f"{stripped} - {next_stripped}"
                    merged_lines.append(merged_heading)
                    i = next_idx + 1
                    continue

        merged_lines.append(line)
        i += 1

    return "\n".join(merged_lines)


def scan_for_prompt_injection(text: str) -> bool:
    """Scan chunk text for suspicious prompt-injection phrases.

    Args:
        text: Text to evaluate.

    Returns:
        True if any prompt injection pattern is detected, otherwise False.
    """
    for pattern in INJECTION_PATTERNS:
        if pattern.search(text):
            return True
    return False


def chunk_document(doc: ExtractedDocument) -> List[ProcessedChunk]:
    """Chunk extracted document sections using RecursiveCharacterTextSplitter with label merging.

    Args:
        doc: ExtractedDocument containing sections.

    Returns:
        List of ProcessedChunk items ready for vectorization.
    """
    settings = get_settings()

    # ~450 tokens ~ 1800 characters; ~60 tokens ~ 240 characters overlap
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.CHUNK_SIZE * 4,  # Approx 1800 chars
        chunk_overlap=settings.CHUNK_OVERLAP * 4,  # Approx 240 chars
        separators=["\n\n", "\n", ". ", " ", ""],
    )

    chunks: List[ProcessedChunk] = []
    chunk_index = 0

    for section in doc.sections:
        # 1. Pre-split label-merging pass
        normalized_content = merge_standalone_labels(section.content)

        # 2. Split section into raw chunks
        raw_chunks = splitter.split_text(normalized_content)

        for raw_text in raw_chunks:
            stripped_raw = raw_text.strip()
            if not stripped_raw:
                continue

            # 3. Prepend [File: {file_name} | Location: {page_or_section}]
            location_str = section.page_or_section or (
                f"Page {section.page_number}" if section.page_number else "Section"
            )
            prefixed_content = (
                f"[File: {doc.filename} | Location: {location_str}]\n{stripped_raw}"
            )

            # 4. Scan for prompt injection warning
            has_warning = scan_for_prompt_injection(stripped_raw)

            # Deterministic/UUID chunk ID
            chunk_id = f"chunk_{uuid.uuid4().hex[:16]}"
            token_count = max(1, len(prefixed_content) // 4)

            chunks.append(
                ProcessedChunk(
                    chunk_id=chunk_id,
                    chunk_index=chunk_index,
                    content=prefixed_content,
                    raw_text=stripped_raw,
                    page_number=section.page_number,
                    section_heading=section.section_heading,
                    page_or_section=location_str,
                    has_injection_warning=has_warning,
                    token_count=token_count,
                )
            )
            chunk_index += 1

    return chunks
