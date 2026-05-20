from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
import re


class AnswerType(StrEnum):
    IRAC_ANALYSIS = "IRAC_ANALYSIS"
    CREAC_MEMORANDUM = "CREAC_MEMORANDUM"
    DEFINITIONAL = "DEFINITIONAL"
    PROCEDURAL_CHECKLIST = "PROCEDURAL_CHECKLIST"
    COMPARATIVE_TABLE = "COMPARATIVE_TABLE"
    REFUSAL = "REFUSAL"


@dataclass(frozen=True, slots=True)
class LegalAnswerContractResult:
    ok: bool
    answer_type: AnswerType
    missing_sections: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
    reason: str | None = None


_DEFINITIONAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"^\s*(what\s+is|what\s+does\s+.+\s+mean|define|meaning\s+of)\b", re.IGNORECASE),
    re.compile(r"\bdefinition\s+of\b", re.IGNORECASE),
)

_PROCEDURAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(steps|procedure|process|how\s+do\s+i|how\s+to|checklist|file|filing)\b", re.IGNORECASE),
)

_COMPARATIVE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(compare|comparison|difference|distinguish\s+between|versus| vs\.? )\b", re.IGNORECASE),
)

_REFUSAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(cannot answer|cannot safely answer|insufficient corpus|not established in retrieved corpus)\b", re.IGNORECASE),
)


def classify_answer_type(prompt: str, *, reasoning_framework: str = "CREAC") -> AnswerType:
    normalized = " ".join(str(prompt or "").split()).strip()
    if not normalized:
        return AnswerType.CREAC_MEMORANDUM
    if any(pattern.search(normalized) for pattern in _REFUSAL_PATTERNS):
        return AnswerType.REFUSAL
    if any(pattern.search(normalized) for pattern in _DEFINITIONAL_PATTERNS):
        return AnswerType.DEFINITIONAL
    if any(pattern.search(normalized) for pattern in _COMPARATIVE_PATTERNS):
        return AnswerType.COMPARATIVE_TABLE
    if any(pattern.search(normalized) for pattern in _PROCEDURAL_PATTERNS):
        return AnswerType.PROCEDURAL_CHECKLIST
    if str(reasoning_framework or "").strip().upper() == "IRAC":
        return AnswerType.IRAC_ANALYSIS
    return AnswerType.CREAC_MEMORANDUM


def validate_irac_answer(text: str) -> LegalAnswerContractResult:
    return _validate_required_sections(
        text,
        answer_type=AnswerType.IRAC_ANALYSIS,
        required=("Issue:", "Rule:", "Application:", "Conclusion:"),
    )


def validate_creac_answer(text: str) -> LegalAnswerContractResult:
    return _validate_required_sections(
        text,
        answer_type=AnswerType.CREAC_MEMORANDUM,
        required=("Conclusion:", "Rule:", "Explanation:", "Application:"),
    )


def validate_answer_contract(text: str, answer_type: AnswerType) -> LegalAnswerContractResult:
    if answer_type == AnswerType.IRAC_ANALYSIS:
        return validate_irac_answer(text)
    if answer_type == AnswerType.CREAC_MEMORANDUM:
        return validate_creac_answer(text)
    if answer_type == AnswerType.DEFINITIONAL:
        return _validate_required_sections(
            text,
            answer_type=answer_type,
            required=("Definition:", "Source:", "Practical Note:"),
        )
    if answer_type == AnswerType.PROCEDURAL_CHECKLIST:
        return _validate_required_sections(
            text,
            answer_type=answer_type,
            required=("Checklist:", "Authority:", "Limits:"),
        )
    if answer_type == AnswerType.COMPARATIVE_TABLE:
        return _validate_required_sections(
            text,
            answer_type=answer_type,
            required=("Comparison:", "Authority:", "Practical Consequence:"),
        )
    if answer_type == AnswerType.REFUSAL:
        return _validate_required_sections(
            text,
            answer_type=answer_type,
            required=("Cannot Safely Answer:", "Reason:", "Next Step:"),
        )
    return LegalAnswerContractResult(
        ok=False,
        answer_type=answer_type,
        reason=f"Unsupported answer type: {answer_type}",
    )


def required_leading_prefix(answer_type: AnswerType) -> str:
    if answer_type == AnswerType.IRAC_ANALYSIS:
        return "Issue:"
    if answer_type == AnswerType.CREAC_MEMORANDUM:
        return "Conclusion:"
    if answer_type == AnswerType.DEFINITIONAL:
        return "Definition:"
    if answer_type == AnswerType.PROCEDURAL_CHECKLIST:
        return "Checklist:"
    if answer_type == AnswerType.COMPARATIVE_TABLE:
        return "Comparison:"
    if answer_type == AnswerType.REFUSAL:
        return "Cannot Safely Answer:"
    return ""


def requires_application_mapping(text: str, *, has_element_evidence: bool) -> bool:
    if not has_element_evidence:
        return False
    normalized = " ".join(str(text or "").lower().split())
    return not ("element" in normalized and ("because" in normalized or "via" in normalized or "source" in normalized))


def _validate_required_sections(
    text: str,
    *,
    answer_type: AnswerType,
    required: tuple[str, ...],
) -> LegalAnswerContractResult:
    source = str(text or "")
    missing = tuple(section for section in required if section not in source)
    warnings: list[str] = []
    prefix = required[0] if required else ""
    if prefix and not source.strip().startswith(prefix):
        warnings.append(f"Answer must start with {prefix}")
    return LegalAnswerContractResult(
        ok=not missing and not warnings,
        answer_type=answer_type,
        missing_sections=missing,
        warnings=tuple(warnings),
        reason=None if not missing and not warnings else "Answer contract failed.",
    )

