from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any


SECONDARY_SOURCE_TYPES = {"textbook", "practicenote", "practice_note", "commentary", "journalarticle", "journal_article"}
PRIMARY_SOURCE_TYPES = {"judgment", "case", "case_law", "act", "statute", "regulation"}
NEUTRAL_CITATION_RE = re.compile(r"\[(?:19|20)\d{2}\]\s*TZ[A-Z]+\s*\d+", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SourceSafetyAssessment:
    secondary_warnings: tuple[str, ...] = field(default_factory=tuple)
    unreported_warnings: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_warnings(self) -> bool:
        return bool(self.secondary_warnings or self.unreported_warnings)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def analyze_source_safety(*, graph_evidence: list[dict[str, Any]] | None) -> SourceSafetyAssessment | None:
    secondary: list[str] = []
    unreported: list[str] = []
    for item in graph_evidence or []:
        reference = _text(item.get("reference") or item.get("citation") or item.get("title")) or "Retrieved source"
        source_type = _normalize(item.get("source_type") or item.get("document_type") or item.get("authority_type"))
        if source_type in SECONDARY_SOURCE_TYPES:
            label = source_type.replace("_", " ").title()
            secondary.append(f"{reference} is a {label}; treat it as persuasive only and never as binding authority.")
            continue
        if source_type and source_type not in PRIMARY_SOURCE_TYPES:
            continue
        if _looks_unreported_case(item):
            missing = _missing_unreported_fields(item)
            if missing:
                unreported.append(
                    f"{reference} appears to be an unreported or irregularly cited case. It needs review before citation because it lacks: {', '.join(missing)}."
                )
    if not secondary and not unreported:
        return None
    return SourceSafetyAssessment(secondary_warnings=tuple(secondary), unreported_warnings=tuple(unreported))


def render_source_safety_application(assessment: SourceSafetyAssessment | None) -> str | None:
    if assessment is None or not assessment.has_warnings:
        return None
    warnings = [*assessment.secondary_warnings, *assessment.unreported_warnings]
    return " ".join(warnings[:3])


def render_source_safety_graph_lines(assessment: SourceSafetyAssessment | None) -> list[str]:
    if assessment is None or not assessment.has_warnings:
        return []
    lines = ["  [SOURCE SAFETY WARNING]"]
    for warning in [*assessment.secondary_warnings, *assessment.unreported_warnings][:4]:
        lines.append(f"  {warning}")
    return lines


def _looks_unreported_case(item: dict[str, Any]) -> bool:
    source_type = _normalize(item.get("document_type") or item.get("source_type") or item.get("authority_type"))
    if source_type not in {"", "judgment", "case", "case_law"}:
        return False
    citation = _text(item.get("citation") or item.get("reference"))
    if citation and NEUTRAL_CITATION_RE.search(citation):
        return False
    return True


def _missing_unreported_fields(item: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if not (_text(item.get("title")) or _text(item.get("parties")) or _text(item.get("reference"))):
        missing.append("title/parties")
    if not _text(item.get("court")):
        missing.append("court")
    if not (_text(item.get("date")) or _text(item.get("publication_date")) or _text(item.get("year"))):
        missing.append("date/year")
    if not (_text(item.get("judge")) or _text(item.get("judge_name")) or _text(item.get("source_pdf_hash")) or _text(item.get("pdf_hash"))):
        missing.append("judge or source PDF hash")
    return missing


def _normalize(value: object) -> str:
    return re.sub(r"\s+", "_", str(value or "").strip().lower())


def _text(value: object) -> str:
    if isinstance(value, (list, tuple)):
        return " ".join(str(item).strip() for item in value if str(item).strip())
    return str(value or "").strip()
