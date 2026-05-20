from __future__ import annotations

import hashlib
import re
from urllib.parse import urljoin, urlparse

TAG_PATTERN = re.compile(r"<[^>]+>")
WHITESPACE_PATTERN = re.compile(r"\s+")
ACT_AMENDMENT_PATTERN = re.compile(
    r"\b(amendment|amending|amended)\b",
    re.IGNORECASE,
)
ACT_AMENDMENT_PURPOSE_PATTERN = re.compile(
    r"\b(an\s+act\s+to\s+amend|to\s+amend\s+the|amends?\s+the)\b",
    re.IGNORECASE,
)
ACT_PRINCIPAL_LEGISLATION_PATTERN = re.compile(
    r"\b(principal\s+legislation|principal\s+act|revised\s+edition|revised\s+edition\s+of|laws\s+revision\s+act)\b",
    re.IGNORECASE,
)
ACT_CURRENT_VERSION_PATTERN = re.compile(
    r"\b(consolidated|revised|updated|edition|as\s+at)\b",
    re.IGNORECASE,
)
TANZLII_ZANZIBAR_PATH_PATTERN = re.compile(r"/en/(judgments|akn/tz/judgment)/z", re.IGNORECASE)
UNION_COURT_PATTERN = re.compile(r"\b(TZCA|CAT|COURT OF APPEAL)\b", re.IGNORECASE)
MAINLAND_COURT_PATTERN = re.compile(r"\b(TZHC|HIGH COURT|RESIDENT MAGISTRATE|DISTRICT COURT|PRIMARY COURT)\b", re.IGNORECASE)
ZANZIBAR_COURT_PATTERN = re.compile(r"\b(HCZ|ZANZIBAR|KADHI|KADHI'S COURT)\b", re.IGNORECASE)
PARLIAMENT_ZANZIBAR_PATTERN = re.compile(
    r"\b(zanzibar|house of representatives|revolutionary government of zanzibar|president of zanzibar|kadhi(?:'s)? court)\b",
    re.IGNORECASE,
)
PARLIAMENT_MAINLAND_PATTERN = re.compile(
    r"\b(mainland tanzania|tanzania mainland|mainland only|excluding zanzibar|other than zanzibar)\b",
    re.IGNORECASE,
)
PARLIAMENT_UNION_PATTERN = re.compile(
    r"\b(union matters?|constitution of the united republic|union government|court of appeal of tanzania|union territory)\b",
    re.IGNORECASE,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def clean_whitespace(value: str) -> str:
    stripped = TAG_PATTERN.sub(" ", value)
    return WHITESPACE_PATTERN.sub(" ", stripped).strip()


def make_absolute_url(base_url: str, url: str) -> str:
    return urljoin(base_url, url)


def get_domain(url: str) -> str:
    return urlparse(url).netloc.lower()


def normalize_act_title(title: str) -> str:
    normalized = title.lower()
    normalized = re.sub(r"\b(the|act|law|of|no\.?|number|chapter|cap\.?|cap)\b", " ", normalized)
    normalized = re.sub(r"\b\d{4}\b", " ", normalized)
    normalized = re.sub(r"\b\d+\b", " ", normalized)
    normalized = re.sub(r"[^a-z\s]", " ", normalized)
    normalized = WHITESPACE_PATTERN.sub(" ", normalized).strip()
    return normalized


def classify_parliament_document(title: str, body_text: str) -> tuple[str, bool]:
    title_text = str(title or "")
    body = str(body_text or "")
    text = f"{title_text} {body}"
    is_amendment = bool(ACT_AMENDMENT_PATTERN.search(title_text)) or bool(ACT_AMENDMENT_PURPOSE_PATTERN.search(text))
    has_principal_legislation_marker = bool(ACT_PRINCIPAL_LEGISLATION_PATTERN.search(text))

    # Amendment signals are stronger than generic "current/principal law" markers.
    # OAGMIS titles frequently contain both, and we want explicit amendment acts to
    # stay typed as amendments for downstream linking and consolidation.
    if is_amendment:
        return "amendment", False

    if has_principal_legislation_marker:
        return "act", True

    is_current_version = bool(ACT_CURRENT_VERSION_PATTERN.search(text))
    if is_current_version:
        return "act", True

    return "act", True


def detect_language_hint(text: str) -> str:
    swahili_terms = ("mahakama", "hukumu", "wakili", "kesi", "dhamana")
    lowered = text.lower()
    if any(term in lowered for term in swahili_terms):
        return "sw"
    return "en"


def classify_tanzanian_jurisdiction(
    *,
    source_name: str,
    source_url: str,
    court: str | None = None,
    title: str = "",
    body_text: str = "",
) -> str:
    normalized_source = str(source_name or "").strip().lower()
    normalized_court = str(court or "").strip().upper()
    combined_text = f"{title}\n{body_text}"

    if normalized_source == "parliament":
        if PARLIAMENT_MAINLAND_PATTERN.search(combined_text):
            return "mainland"
        if PARLIAMENT_ZANZIBAR_PATTERN.search(combined_text) or PARLIAMENT_ZANZIBAR_PATTERN.search(source_url):
            return "zanzibar"
        if PARLIAMENT_UNION_PATTERN.search(combined_text):
            return "union"
        return "unknown"

    if normalized_source == "tanzlii":
        if TANZLII_ZANZIBAR_PATH_PATTERN.search(source_url):
            return "zanzibar"
        if ZANZIBAR_COURT_PATTERN.search(normalized_court) or ZANZIBAR_COURT_PATTERN.search(combined_text):
            return "zanzibar"
        if UNION_COURT_PATTERN.search(normalized_court) or UNION_COURT_PATTERN.search(combined_text):
            return "union"
        if MAINLAND_COURT_PATTERN.search(normalized_court) or MAINLAND_COURT_PATTERN.search(combined_text):
            return "mainland"

    return "unknown"
