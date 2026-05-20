from __future__ import annotations

from dataclasses import asdict, dataclass, field
import re
from typing import Any


ACTIVE_THRESHOLD = 0.75
REVIEW_THRESHOLD = 0.45


@dataclass(frozen=True, slots=True)
class InterpretationSectionMatch:
    should_materialize: bool
    status: str
    score: float
    reasons: tuple[str, ...] = field(default_factory=tuple)
    ratio_quote: str = ""
    ratio_paragraph: str = ""
    section_number: str = ""
    section_version_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def score_ratio_section_interpretation(
    *,
    ratio: dict[str, Any],
    resolved_statute: dict[str, Any],
) -> InterpretationSectionMatch:
    quote = _first_text(ratio, "quote", "text")
    interpretation = _first_text(ratio, "interpretation", "interpretation_text", "holding", "principle_text")
    source_paragraph = _first_text(ratio, "source_paragraph", "paragraph_text", "paragraph")
    ratio_type = _first_text(ratio, "ratio_type", "type", "statement_type", "classification")
    section_number = _normalize_section_number(
        resolved_statute.get("section_number")
        or resolved_statute.get("section_ref")
        or resolved_statute.get("normalized_section_ref")
    )
    section_version_id = str(
        resolved_statute.get("active_section_version_id")
        or resolved_statute.get("section_version_id")
        or ""
    ).strip()
    reasons: list[str] = []
    score = 0.0

    if not quote.strip():
        return InterpretationSectionMatch(
            should_materialize=False,
            status="skipped",
            score=0.0,
            reasons=("missing_ratio_quote",),
            section_number=section_number,
            section_version_id=section_version_id,
        )
    if not section_number or not section_version_id:
        return InterpretationSectionMatch(
            should_materialize=False,
            status="skipped",
            score=0.0,
            reasons=("missing_section_target",),
            ratio_quote=quote,
            ratio_paragraph=source_paragraph,
            section_number=section_number,
            section_version_id=section_version_id,
        )

    quote_has_section = _contains_exact_section_ref(quote, section_number)
    interpretation_has_section = _contains_exact_section_ref(interpretation, section_number)
    paragraph_has_section = _contains_exact_section_ref(source_paragraph, section_number)
    if quote_has_section:
        score += 0.45
        reasons.append("exact_section_ref_in_ratio_quote")
    elif interpretation_has_section:
        score += 0.25
        reasons.append("exact_section_ref_in_interpretation_text")
    elif paragraph_has_section:
        score += 0.15
        reasons.append("section_ref_only_in_source_paragraph")
    else:
        return InterpretationSectionMatch(
            should_materialize=False,
            status="skipped",
            score=0.0,
            reasons=("no_exact_section_ref_in_ratio",),
            ratio_quote=quote,
            ratio_paragraph=source_paragraph,
            section_number=section_number,
            section_version_id=section_version_id,
        )

    act_name = _first_text(resolved_statute, "act_name", "act_title", "canonical_act_title")
    if act_name and _act_name_in_text(act_name, " ".join([quote, interpretation])):
        score += 0.20
        reasons.append("act_name_in_ratio_text")
    elif act_name and _act_name_compatible(act_name, _first_text(resolved_statute, "act_title")):
        score += 0.10
        reasons.append("citation_act_matches_resolved_act")

    if _looks_interpretive(" ".join([ratio_type, quote, interpretation])):
        score += 0.20
        reasons.append("ratio_language_is_interpretive")
    elif _looks_applicative_only(" ".join([ratio_type, quote, interpretation])):
        reasons.append("language_is_applicative_not_interpretive")
    else:
        score += 0.05
        reasons.append("generic_ratio_language")

    proximity = _paragraph_proximity(ratio, resolved_statute)
    if proximity == 0:
        score += 0.15
        reasons.append("same_paragraph_as_statute_citation")
    elif proximity is not None and proximity <= 1:
        score += 0.10
        reasons.append("nearby_paragraph_to_statute_citation")
    elif proximity is not None:
        reasons.append("statute_citation_not_near_ratio_paragraph")

    score = min(1.0, round(score, 3))
    if score >= ACTIVE_THRESHOLD and quote_has_section:
        status = "active"
        should_materialize = True
    elif score >= REVIEW_THRESHOLD:
        status = "needs_review"
        should_materialize = True
    else:
        status = "skipped"
        should_materialize = False
    return InterpretationSectionMatch(
        should_materialize=should_materialize,
        status=status,
        score=score,
        reasons=tuple(reasons),
        ratio_quote=quote,
        ratio_paragraph=source_paragraph,
        section_number=section_number,
        section_version_id=section_version_id,
    )


def _contains_exact_section_ref(text: str, section_number: str) -> bool:
    normalized = _normalize_section_number(section_number)
    if not normalized or not str(text or "").strip():
        return False
    escaped = re.escape(normalized)
    patterns = (
        rf"\bsection\s+{escaped}\b",
        rf"\bs\.\s*{escaped}\b",
        rf"\bsec\.\s*{escaped}\b",
        rf"\b{escaped}\s+of\s+the\s+[A-Z][A-Za-z\s]+Act\b",
    )
    return any(re.search(pattern, text, flags=re.IGNORECASE) for pattern in patterns)


def _normalize_section_number(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip().lower())
    return re.sub(r"^section", "", text)


def _first_text(mapping: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(mapping.get(key) or "").strip()
        if value:
            return value
    return ""


def _act_name_in_text(act_name: str, text: str) -> bool:
    act_tokens = _tokens(act_name)
    text_tokens = _tokens(text)
    if not act_tokens or not text_tokens:
        return False
    return len(act_tokens & text_tokens) / max(1, len(act_tokens)) >= 0.65


def _act_name_compatible(left: str, right: str) -> bool:
    left_tokens = _tokens(left)
    right_tokens = _tokens(right)
    if not left_tokens or not right_tokens:
        return False
    return len(left_tokens & right_tokens) / max(1, min(len(left_tokens), len(right_tokens))) >= 0.75


def _tokens(value: str) -> set[str]:
    stop = {"the", "of", "and", "act", "cap", "chapter", "no"}
    return {token for token in re.split(r"[^a-z0-9]+", str(value or "").lower()) if len(token) > 2 and token not in stop}


def _looks_interpretive(text: str) -> bool:
    return bool(
        re.search(
            r"\b(interpret|interpreted|construction|construe|construed|meaning|means|scope|purport|effect|properly read|read together|ambit)\b",
            text,
            flags=re.IGNORECASE,
        )
    )


def _looks_applicative_only(text: str) -> bool:
    return bool(re.search(r"\b(apply|applied|applicable|cited|relied on|mentioned)\b", text, flags=re.IGNORECASE))


def _paragraph_proximity(ratio: dict[str, Any], resolved_statute: dict[str, Any]) -> int | None:
    ratio_para = _paragraph_number(
        ratio.get("paragraph_number")
        or ratio.get("paragraph")
        or ratio.get("source_paragraph_number")
        or ratio.get("source_paragraph")
    )
    statute_para = _paragraph_number(
        resolved_statute.get("paragraph_number")
        or resolved_statute.get("source_paragraph_number")
        or resolved_statute.get("source_paragraph")
        or resolved_statute.get("citation_paragraph")
    )
    if ratio_para is None or statute_para is None:
        return None
    return abs(ratio_para - statute_para)


def _paragraph_number(value: object) -> int | None:
    if isinstance(value, int):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    match = re.search(r"\b(?:para(?:graph)?\.?\s*)?(\d{1,4})\b", text, flags=re.IGNORECASE)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None
