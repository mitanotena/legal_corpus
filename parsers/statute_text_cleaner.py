from __future__ import annotations

import re


WATERMARK_PATTERNS = (
    r"\bG\.\s*A\s*O\b",
    r"\bof\s+n\s+o\s+ssi\s+mi\s+er\s+p\s+ut\b",
    r"\bwit\s+d\s+e\s+but\s+distri\s+or\s+d\s+e\b",
    r"\bc\s+u\s+d\s+o\s+pr\s+e\s+e\s+r\s+b\s+y\s+a\s+m\b",
    r"\bk\s+o\s+o\s+b\s+s\s+hi\b",
    r"\bof\s+t\s+a\s+r\s+p\b",
    r"\bni\s+a\s+nz\s+Ta\b",
    r"\bof\s+nt\s+e\s+m\s+n\s+er\s+ov\b",
    r"\b5\s+2\s+20\s+©\b",
)


HEADER_FOOTER_RE = re.compile(
    r"(?:^|\n)\s*(?:THE\s+[A-Z][A-Z\s]+\s+ACT\s+\[CAP\.[^\n]{1,80}\]|\[CAP\.[^\n]{1,80}\])\s*(?:\n|$)"
)


def clean_statute_ocr_text(value: str) -> str:
    """Remove repeated PDF/OCR chrome while preserving statutory wording.

    The cleaner is intentionally conservative: it removes known OAG watermark
    token streams and page headers, but does not infer legal words.
    """

    text = str(value or "")
    text = text.replace("\u2018", '"').replace("\u2019", '"').replace("\u201c", '"').replace("\u201d", '"')
    text = text.replace("\ufeff", " ")
    text = re.sub(r"\f+", "\n", text)
    text = HEADER_FOOTER_RE.sub("\n", text)
    for pattern in WATERMARK_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\bActs?\s+Nos?\.\s+(?:\d+\s+of\s+\d{4}\s+s\.\s+\d+[A-Z]?\s*;?\s*){4,}", " ", text, flags=re.IGNORECASE)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"\n[ \t]+", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def statute_ocr_noise_score(value: str) -> float:
    text = str(value or "")
    if not text:
        return 1.0
    lowered = text.lower()
    hits = sum(1 for pattern in WATERMARK_PATTERNS if re.search(pattern, lowered, flags=re.IGNORECASE))
    broken_word_hits = len(re.findall(r"\b[a-z]{1,2}\s+[a-z]{1,2}\s+[a-z]{1,2}\s+[a-z]{1,2}\b", lowered))
    form_feeds = text.count("\f")
    return (hits * 10 + broken_word_hits + form_feeds) / max(len(text) / 1000.0, 1.0)
