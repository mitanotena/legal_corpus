from __future__ import annotations

import html
import hashlib
import re
from dataclasses import dataclass, field

from shared.legal_corpus.parsers.statute_text_cleaner import clean_statute_ocr_text


SECTION_HEADING_RE = re.compile(
    r"(?im)^\s*(?:section\s+)?(?P<number>[0-9]+[A-Za-z]?)\s*[\.\-\)\:]\s+(?P<title>[^\n]{1,180})$"
)
INLINE_SECTION_MARKER_RE = re.compile(r"(?<!Cap\. )(?<!No\. )\b(?P<number>[0-9]{1,3}[A-Za-z]?)\.\s+")
PART_OR_SCHEDULE_RE = re.compile(r"(?im)^\s*(?:schedule|first schedule|second schedule|table)\b")
SUBSECTION_RE = re.compile(r"(?m)(?P<label>\([0-9]+\)|\([a-z]\)|\([ivxlcdm]+\))")
DEFINITION_RE = re.compile(
    r'["“](?P<term>[^"”]{2,120})["”]\s+means\s+(?P<definition>.*?)(?=(?:;\s*["“][^"”]+["”]\s+means)|(?:\.\s*$)|$)',
    re.IGNORECASE | re.DOTALL,
)
TAG_RE = re.compile(r"<[^>]+>")


@dataclass(frozen=True)
class ParsedDefinition:
    term: str
    definition: str
    section_number: str


@dataclass(frozen=True)
class ParsedSection:
    section_number: str
    title: str
    text: str
    parent_section_number: str | None = None
    section_kind: str = "section"
    definitions: tuple[ParsedDefinition, ...] = field(default_factory=tuple)
    source_start_char: int | None = None
    source_end_char: int | None = None
    source_text_sha256: str | None = None
    cleaned_section_sha256: str | None = None


@dataclass(frozen=True)
class ParsedAct:
    sections: tuple[ParsedSection, ...]
    definitions: tuple[ParsedDefinition, ...]


def html_to_text(raw: str) -> str:
    text = str(raw or "")
    text = re.sub(r"(?is)<(script|style).*?>.*?</\1>", "\n", text)
    text = re.sub(r"(?i)<br\s*/?>", "\n", text)
    text = re.sub(r"(?i)</(?:p|div|section|article|li|h[1-6]|tr)>", "\n", text)
    text = TAG_RE.sub(" ", text)
    text = html.unescape(text)
    text = text.replace("\u00a0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return clean_statute_ocr_text(text.strip())


def normalize_section_number(value: str) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip())
    text = re.sub(r"(?i)^section", "", text)
    return text


def _clean_text(value: str) -> str:
    text = clean_statute_ocr_text(str(value or ""))
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n\s+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _trimmed_span(text: str, start: int, end: int) -> tuple[int, int, str]:
    while start < end and text[start].isspace():
        start += 1
    while end > start and text[end - 1].isspace():
        end -= 1
    return start, end, text[start:end]


def _sha256_text(value: str) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def _section_blocks(text: str) -> list[tuple[str, str, str, int, int, str]]:
    matches = list(SECTION_HEADING_RE.finditer(text))
    blocks: list[tuple[str, str, str, int, int, str]] = []
    for index, match in enumerate(matches):
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        source_start, source_end, source_block = _trimmed_span(text, start, end)
        block = source_block.strip()
        if PART_OR_SCHEDULE_RE.search(block.splitlines()[0] if block else ""):
            continue
        number = normalize_section_number(match.group("number"))
        title = _clean_text(match.group("title"))
        blocks.append((number, title, block, source_start, source_end, source_block))
    if len(blocks) >= 5:
        return blocks

    inline_matches = [
        match
        for match in INLINE_SECTION_MARKER_RE.finditer(text)
        if 1 <= int(re.match(r"\d+", match.group("number")).group(0)) <= 999
    ]
    inline_blocks: list[tuple[str, str, str, int, int, str]] = []
    for index, match in enumerate(inline_matches):
        start = match.start()
        end = inline_matches[index + 1].start() if index + 1 < len(inline_matches) else len(text)
        source_start, source_end, source_block = _trimmed_span(text, start, end)
        block = _clean_text(source_block)
        if len(block) < 40:
            continue
        number = normalize_section_number(match.group("number"))
        title_source = re.sub(rf"^{re.escape(match.group(0))}", "", block).strip()
        title = _clean_text(re.split(r"(?<=[.;])\s+", title_source, maxsplit=1)[0])[:120] or f"Section {number}"
        inline_blocks.append((number, title, block, source_start, source_end, source_block))
    if len(inline_blocks) > len(blocks):
        return inline_blocks
    return blocks


def _split_subsections(section_number: str, section_text: str, *, parent_source_start: int | None = None) -> list[ParsedSection]:
    body_start = section_text.find("\n")
    body = section_text[body_start + 1 :] if body_start >= 0 else section_text
    body_source_start = (parent_source_start + body_start + 1) if parent_source_start is not None and body_start >= 0 else parent_source_start
    markers = list(SUBSECTION_RE.finditer(body))
    if not markers:
        return []

    parsed: list[ParsedSection] = []
    stack: list[str] = [section_number]
    for index, marker in enumerate(markers):
        label = marker.group("label").lower()
        value = label[1:-1]
        end = markers[index + 1].start() if index + 1 < len(markers) else len(body)
        source_chunk = body[marker.start() : end]
        chunk = _clean_text(source_chunk)
        if not chunk:
            continue
        source_start = (body_source_start + marker.start()) if body_source_start is not None else None
        source_end = (body_source_start + end) if body_source_start is not None else None

        is_roman = bool(re.fullmatch(r"[ivxlcdm]+", value))
        if value.isdigit():
            stack = [section_number, label]
        elif is_roman and len(stack) >= 3:
            stack = stack[:3]
            stack.append(label)
        elif re.fullmatch(r"[a-z]", value):
            stack = stack[:2] if len(stack) >= 2 else [section_number]
            stack.append(label)
        else:
            stack = stack[:3] if len(stack) >= 3 else [section_number, label]
            stack.append(label)
        subsection_number = section_number + "".join(stack[1:])
        parent = section_number + "".join(stack[1:-1]) if len(stack) > 2 else section_number
        parsed.append(
            ParsedSection(
                section_number=subsection_number,
                title=f"Section {subsection_number}",
                text=chunk,
                parent_section_number=parent,
                section_kind="subsection",
                source_start_char=source_start,
                source_end_char=source_end,
                source_text_sha256=_sha256_text(source_chunk),
                cleaned_section_sha256=_sha256_text(chunk),
            )
        )
    return parsed


def _parse_definitions(section_number: str, text: str) -> tuple[ParsedDefinition, ...]:
    definitions: list[ParsedDefinition] = []
    if normalize_section_number(section_number) != "2":
        return tuple()
    for match in DEFINITION_RE.finditer(text):
        term = _clean_text(match.group("term")).strip('"')
        definition = _clean_text(match.group("definition").rstrip(" ;."))
        if term and definition:
            definitions.append(ParsedDefinition(term=term, definition=definition, section_number=section_number))
    return tuple(definitions)


class ActTextParser:
    """Deterministic parser for consolidated Act text. It never calls an LLM."""

    def parse(self, raw_text: str) -> ParsedAct:
        text = html_to_text(raw_text)
        sections: list[ParsedSection] = []
        definitions: list[ParsedDefinition] = []
        for section_number, title, block, source_start, source_end, source_block in _section_blocks(text):
            clean_block = _clean_text(block)
            section_definitions = _parse_definitions(section_number, clean_block)
            section = ParsedSection(
                section_number=section_number,
                title=title,
                text=clean_block,
                section_kind="section",
                definitions=section_definitions,
                source_start_char=source_start,
                source_end_char=source_end,
                source_text_sha256=_sha256_text(source_block),
                cleaned_section_sha256=_sha256_text(clean_block),
            )
            sections.append(section)
            sections.extend(_split_subsections(section_number, source_block, parent_source_start=source_start))
            definitions.extend(section_definitions)
        return ParsedAct(sections=tuple(sections), definitions=tuple(definitions))
