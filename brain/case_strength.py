from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class CaseStrengthStatus(StrEnum):
    STRONG = "strong"
    LIKELY_FAVORABLE_BUT_INCOMPLETE = "likely_favorable_but_incomplete"
    MODERATE = "moderate"
    CANNOT_ASSESS_COMPLETENESS = "cannot_assess_completeness"
    WEAK = "weak"
    APPEARS_WEAK_BUT_INCOMPLETE = "appears_weak_but_incomplete"


@dataclass(frozen=True, slots=True)
class CaseStrengthAssessment:
    status: CaseStrengthStatus
    matrix_row: str
    matrix_column: str
    satisfied_elements: tuple[str, ...] = ()
    failed_elements: tuple[str, ...] = ()
    insufficient_elements: tuple[str, ...] = ()
    ranked_weaknesses: tuple[str, ...] = ()
    opponent_argument: str = ""
    jurisdictional_challenges: tuple[str, ...] = ()
    adverse_authority: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        return payload


def evaluate_case_strength(
    *,
    prompt: str,
    graph_evidence: list[dict[str, Any]] | None = None,
    missing_facts: list[str] | None = None,
    filtered_authorities: list[dict[str, Any]] | None = None,
) -> CaseStrengthAssessment:
    satisfied: list[str] = []
    failed: list[str] = []
    insufficient: list[str] = []
    weaknesses: list[str] = []
    adverse_authority: list[str] = []

    for item in graph_evidence or []:
        reference = _clean(item.get("reference"))
        for test in list(item.get("legal_tests") or []):
            for element in list(test.get("elements") or []):
                if not isinstance(element, dict):
                    continue
                label = _clean(element.get("label"))
                if not label:
                    continue
                result = dict(element.get("result") or {})
                status = _clean(result.get("status")).lower()
                source_text = _clean(result.get("source_text"))
                if status == "failed":
                    failed.append(label)
                    weaknesses.append(_weakness_line(label=label, source_text=source_text, reference=reference))
                elif status == "satisfied":
                    satisfied.append(label)
                else:
                    insufficient.append(label)
        for alert in list(item.get("conflict_alerts") or []):
            counterpart = _clean(alert.get("counterpart_reference"))
            if counterpart:
                adverse_authority.append(counterpart)
                weaknesses.append(f"Adverse or conflicting authority must be confronted: {counterpart}.")
        for signal in list(item.get("doctrinal_signals") or []):
            relation = _clean(signal.get("relation")).lower()
            counterpart = _clean(signal.get("counterpart_reference"))
            if counterpart and relation in {"overruled", "reversed", "not_followed", "conflicts_with"}:
                adverse_authority.append(counterpart)
                weaknesses.append(f"Hostile treatment signal {relation.replace('_', ' ')} points to {counterpart}.")

    for fact in missing_facts or []:
        fact_text = _clean(fact)
        if fact_text:
            insufficient.append(fact_text)
            weaknesses.append(f"Missing material fact: {fact_text}.")

    for authority in filtered_authorities or []:
        status = _clean(authority.get("authority_status") or authority.get("status")).lower()
        reference = _clean(authority.get("reference") or authority.get("title"))
        if reference and status in {"overruled", "reversed", "questioned", "not_followed", "needs_review"}:
            adverse_authority.append(reference)
            weaknesses.append(f"Authority status weakens reliance on {reference}: {status.replace('_', ' ')}.")

    jurisdictional_challenges = _detect_jurisdictional_challenges(prompt)
    weaknesses.extend(jurisdictional_challenges)

    row = _matrix_row(satisfied=satisfied, failed=failed, adverse_authority=adverse_authority, jurisdictional_challenges=jurisdictional_challenges)
    column = "Insufficient Evidence" if insufficient or missing_facts or _is_sparse_merits_record(satisfied=satisfied, failed=failed, adverse_authority=adverse_authority) else "Sufficient Evidence"
    status = _matrix_status(row=row, column=column)
    ranked_weaknesses = tuple(_dedupe(weaknesses)[:6])
    opponent_argument = _opponent_argument(
        status=status,
        failed=failed,
        insufficient=insufficient,
        jurisdictional_challenges=jurisdictional_challenges,
        adverse_authority=adverse_authority,
    )
    return CaseStrengthAssessment(
        status=status,
        matrix_row=row,
        matrix_column=column,
        satisfied_elements=tuple(_dedupe(satisfied)),
        failed_elements=tuple(_dedupe(failed)),
        insufficient_elements=tuple(_dedupe(insufficient)),
        ranked_weaknesses=ranked_weaknesses,
        opponent_argument=opponent_argument,
        jurisdictional_challenges=tuple(_dedupe(jurisdictional_challenges)),
        adverse_authority=tuple(_dedupe(adverse_authority)),
    )


def build_case_strength_arguments(assessment: CaseStrengthAssessment) -> tuple[list[str], list[str], list[str]]:
    support: list[str] = []
    if assessment.satisfied_elements:
        support.append(
            "Favorable elements: " + ", ".join(assessment.satisfied_elements[:4]) + "."
        )
    else:
        support.append("No element is treated as safely favorable unless the retrieved evidence supports it.")

    opposition = [
        f"Case-strength matrix: {assessment.status.value} ({assessment.matrix_row} / {assessment.matrix_column}).",
        assessment.opponent_argument,
    ]
    opposition.extend(assessment.ranked_weaknesses[:4])

    rebuttals = [
        "Rebut by curing, or cure directly, the highest-ranked failed or missing element with verified record evidence.",
        "Do not overstate the case until jurisdiction, burden, and adverse authority weaknesses are answered.",
    ]
    if assessment.jurisdictional_challenges:
        rebuttals.insert(0, "Resolve the jurisdictional defect before relying on the merits.")
    return support, _dedupe(opposition), _dedupe(rebuttals)


def _matrix_row(
    *,
    satisfied: list[str],
    failed: list[str],
    adverse_authority: list[str],
    jurisdictional_challenges: list[str],
) -> str:
    if failed or adverse_authority or jurisdictional_challenges:
        return "Unfavorable elements"
    if satisfied:
        return "Favorable elements"
    return "Mixed elements"


def _matrix_status(*, row: str, column: str) -> CaseStrengthStatus:
    if row == "Favorable elements" and column == "Sufficient Evidence":
        return CaseStrengthStatus.STRONG
    if row == "Favorable elements":
        return CaseStrengthStatus.LIKELY_FAVORABLE_BUT_INCOMPLETE
    if row == "Mixed elements" and column == "Sufficient Evidence":
        return CaseStrengthStatus.MODERATE
    if row == "Mixed elements":
        return CaseStrengthStatus.CANNOT_ASSESS_COMPLETENESS
    if row == "Unfavorable elements" and column == "Sufficient Evidence":
        return CaseStrengthStatus.WEAK
    return CaseStrengthStatus.APPEARS_WEAK_BUT_INCOMPLETE


def _is_sparse_merits_record(*, satisfied: list[str], failed: list[str], adverse_authority: list[str]) -> bool:
    return not satisfied and not failed and not adverse_authority


def _opponent_argument(
    *,
    status: CaseStrengthStatus,
    failed: list[str],
    insufficient: list[str],
    jurisdictional_challenges: list[str],
    adverse_authority: list[str],
) -> str:
    if jurisdictional_challenges:
        return f"Opposing counsel's first attack is jurisdictional: {jurisdictional_challenges[0]}"
    if failed:
        return f"Opposing counsel will say the case is weak because the element of {failed[0]} failed."
    if adverse_authority:
        return f"Opposing counsel will lead with adverse authority: {adverse_authority[0]}."
    if insufficient:
        return f"Opposing counsel will attack the incomplete record, especially {insufficient[0]}."
    if status == CaseStrengthStatus.STRONG:
        return "Opposing counsel will likely narrow the rule, distinguish the facts, or attack procedural posture."
    return "Opposing counsel will attack factual gaps, legal uncertainty, and any overstatement beyond verified authority."


def _weakness_line(*, label: str, source_text: str, reference: str) -> str:
    suffix = f" Source: {source_text}" if source_text else ""
    ref = f" in {reference}" if reference else ""
    return f"Failed element{ref}: {label}.{suffix}"


def _detect_jurisdictional_challenges(prompt: str) -> list[str]:
    normalized = _clean(prompt).lower()
    challenges: list[str] = []
    if "zanzibar" in normalized and ("mainland" in normalized or "high court of tanzania" in normalized):
        challenges.append("The facts mention Zanzibar but also Mainland forum/law; confirm the proper jurisdictional track before relying on the merits.")
    if "kadhi" in normalized and "mainland" in normalized:
        challenges.append("Kadhi or Islamic family-law facts may require a distinct jurisdictional analysis rather than ordinary Mainland assumptions.")
    return challenges


def _clean(value: object) -> str:
    return " ".join(str(value or "").split()).strip()


def _dedupe(values: list[str] | tuple[str, ...]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = _clean(value)
        key = normalized.lower()
        if not normalized or key in seen:
            continue
        seen.add(key)
        output.append(normalized)
    return output
