from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any


VALID_DISTINCTION_TYPES = {"facts", "law", "procedure", "unclear"}


@dataclass(frozen=True, slots=True)
class DistinguishingEntry:
    source_reference: str
    distinguished_reference: str
    distinction_type: str
    distinction_reason: str
    distinguishing_facts: tuple[str, ...] = field(default_factory=tuple)
    distinguishing_legal_principle: str = ""
    quote: str = ""
    source_paragraph: str = ""
    confidence: float = 0.0
    needs_review: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["distinguishing_facts"] = list(self.distinguishing_facts)
        return payload


@dataclass(frozen=True, slots=True)
class DistinguishingAssessment:
    entries: tuple[DistinguishingEntry, ...]

    @property
    def has_distinguishing_guidance(self) -> bool:
        return bool(self.entries)

    def to_dict(self) -> dict[str, Any]:
        return {"entries": [entry.to_dict() for entry in self.entries]}


def analyze_distinguishing(
    *,
    graph_evidence: list[dict[str, Any]] | None,
) -> DistinguishingAssessment | None:
    entries: list[DistinguishingEntry] = []
    seen: set[tuple[str, str, str]] = set()
    for item in graph_evidence or []:
        source_reference = _text(item.get("reference") or item.get("citation") or item.get("title"))
        for signal in list(item.get("doctrinal_signals") or []):
            if not isinstance(signal, dict):
                continue
            relation = _normalize(signal.get("relation"))
            if relation not in {"distinguishes", "distinguished", "distinguished_on_facts", "distinguished_on_law"}:
                continue
            entry = distinguishing_entry_from_mapping(signal, source_reference=source_reference)
            if entry is None:
                continue
            key = (
                entry.source_reference.lower(),
                entry.distinguished_reference.lower(),
                entry.distinction_reason.lower(),
            )
            if key in seen:
                continue
            seen.add(key)
            entries.append(entry)
    if not entries:
        return None
    entries.sort(key=lambda entry: (entry.needs_review, -entry.confidence, entry.distinguished_reference))
    return DistinguishingAssessment(entries=tuple(entries))


def distinguishing_entry_from_mapping(value: dict[str, Any], *, source_reference: str = "") -> DistinguishingEntry | None:
    metadata = value.get("metadata")
    metadata = dict(metadata) if isinstance(metadata, dict) else {}
    distinguished_reference = _text(
        value.get("distinguished_reference")
        or value.get("counterpart_reference")
        or value.get("target_reference")
        or metadata.get("canonical_citation")
        or metadata.get("citation_text")
    )
    if not distinguished_reference:
        return None
    quote = _text(
        value.get("quote")
        or value.get("evidence_excerpt")
        or value.get("context_excerpt")
        or metadata.get("quote")
        or metadata.get("context_excerpt")
        or metadata.get("evidence_excerpt")
    )
    reason = _text(
        value.get("distinction_reason")
        or value.get("distinguishing_reason")
        or metadata.get("distinction_reason")
        or metadata.get("distinguishing_reason")
    )
    distinguishing_facts = _tuple_texts(
        value.get("distinguishing_facts")
        or metadata.get("distinguishing_facts")
        or metadata.get("facts")
    )
    legal_principle = _text(
        value.get("distinguishing_legal_principle")
        or metadata.get("distinguishing_legal_principle")
        or metadata.get("legal_principle")
    )
    classification = classify_distinction(
        distinction_type=value.get("distinction_type") or metadata.get("distinction_type"),
        reason=reason,
        quote=quote,
        distinguishing_facts=distinguishing_facts,
        distinguishing_legal_principle=legal_principle,
    )
    if not reason:
        reason = quote or "No quoted reason was extracted; review the judgment before relying on this distinction."
    needs_review = classification == "unclear" or not quote or reason.startswith("No quoted reason")
    return DistinguishingEntry(
        source_reference=source_reference,
        distinguished_reference=distinguished_reference,
        distinction_type=classification,
        distinction_reason=reason,
        distinguishing_facts=distinguishing_facts,
        distinguishing_legal_principle=legal_principle,
        quote=quote,
        source_paragraph=_text(value.get("source_paragraph") or metadata.get("source_paragraph") or metadata.get("paragraph_anchor")),
        confidence=max(0.0, min(1.0, float(value.get("confidence") or metadata.get("treatment_confidence") or 0.0))),
        needs_review=needs_review,
    )


def classify_distinction(
    *,
    distinction_type: object = None,
    reason: object = "",
    quote: object = "",
    distinguishing_facts: tuple[str, ...] | list[str] | None = None,
    distinguishing_legal_principle: object = "",
) -> str:
    explicit = _normalize(distinction_type)
    explicit_map = {
        "fact": "facts",
        "facts": "facts",
        "factual": "facts",
        "law": "law",
        "legal": "law",
        "principle": "law",
        "doctrinal": "law",
        "procedure": "procedure",
        "procedural": "procedure",
        "jurisdiction": "procedure",
        "limitation": "procedure",
        "unclear": "unclear",
        "unknown": "unclear",
    }
    if explicit in explicit_map:
        return explicit_map[explicit]

    text = _normalize(" ".join([_text(reason), _text(quote), _text(distinguishing_legal_principle)]))
    fact_count = _count_tokens(text, ("fact", "facts", "evidence", "witness", "circumstance", "distinguishable facts", "different facts"))
    law_count = _count_tokens(text, ("principle", "law", "statute", "section", "rule", "test", "doctrine", "ratio"))
    procedure_count = _count_tokens(text, ("procedure", "procedural", "jurisdiction", "limitation", "time barred", "leave", "appeal", "pleading"))
    if distinguishing_facts:
        fact_count += 2
    if _text(distinguishing_legal_principle):
        law_count += 2
    counts = {"facts": fact_count, "law": law_count, "procedure": procedure_count}
    best_type, best_score = max(counts.items(), key=lambda item: item[1])
    if best_score <= 0:
        return "unclear"
    tied = [key for key, score in counts.items() if score == best_score]
    return best_type if len(tied) == 1 else "unclear"


def render_distinguishing_application(assessment: DistinguishingAssessment | None) -> str | None:
    if assessment is None or not assessment.entries:
        return None
    entry = assessment.entries[0]
    review_suffix = " This distinction is incomplete and needs review before relying on it." if entry.needs_review else ""
    return (
        f"Why the case was distinguished: {entry.source_reference or 'The retrieved authority'} distinguished "
        f"{entry.distinguished_reference} on {entry.distinction_type}. Reason: {entry.distinction_reason}.{review_suffix}"
    )


def render_distinguishing_graph_lines(assessment: DistinguishingAssessment | None) -> list[str]:
    if assessment is None or not assessment.entries:
        return []
    lines = ["  [DISTINGUISHING ANALYSIS]"]
    for entry in assessment.entries[:3]:
        lines.append(f"  Distinguished Authority: {entry.distinguished_reference}")
        lines.append(f"  Distinction Type: {entry.distinction_type}")
        lines.append(f"  Reason: {entry.distinction_reason}")
        if entry.distinguishing_facts:
            lines.append(f"  Distinguishing Facts: {'; '.join(entry.distinguishing_facts[:3])}")
        if entry.distinguishing_legal_principle:
            lines.append(f"  Distinguishing Legal Principle: {entry.distinguishing_legal_principle}")
        if entry.quote:
            lines.append(f"  Quote Evidence: {entry.quote}")
        if entry.needs_review:
            lines.append("  Review Status: needs review because the distinction reason or quote evidence is incomplete.")
    return lines


def _tuple_texts(value: object) -> tuple[str, ...]:
    if isinstance(value, (list, tuple)):
        return tuple(_text(item) for item in value if _text(item))
    text = _text(value)
    return (text,) if text else tuple()


def _count_tokens(text: str, tokens: tuple[str, ...]) -> int:
    return sum(1 for token in tokens if token in text)


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ").strip().lower())


def _text(value: object) -> str:
    return str(value or "").strip()
