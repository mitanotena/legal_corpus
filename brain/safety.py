from __future__ import annotations

from typing import Any


CERTAINTY_MARKERS = (
    "will definitely",
    "guaranteed",
    "certainly win",
    "must succeed",
    "cannot fail",
)


def find_unverified_propositions(*, answer_body: str, filtered_authorities: list[dict[str, Any]]) -> list[str]:
    lowered = answer_body.lower()
    issues: list[str] = []
    grounded_count = len(filtered_authorities)
    if grounded_count <= 0:
        issues.append("The answer is not grounded in a verified authority set.")

    for marker in CERTAINTY_MARKERS:
        if marker in lowered:
            issues.append(f"Unsupported certainty language detected: '{marker}'.")

    return issues


def authority_weight(authority: dict[str, Any]) -> float:
    document_type = str(authority.get("document_type") or "").strip().lower()
    instrument_type = str(authority.get("instrument_type") or "").strip().lower()
    court = str(authority.get("court") or "").strip().lower()

    if instrument_type == "constitution" or document_type == "constitution":
        return 1.0
    if document_type in {"act", "amendment"}:
        return 0.92
    if document_type in {"regulation", "rule"}:
        return 0.82
    if court in {"court of appeal", "supreme court"}:
        return 0.88
    if document_type in {"judgment", "case", "decision"}:
        return 0.76
    return 0.55


def disclaimer_required(*, confidence_score: float) -> bool:
    return confidence_score < 0.85
