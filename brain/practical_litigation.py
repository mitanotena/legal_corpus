from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class PracticalOutcome:
    reference: str
    damages_awarded: str = ""
    costs_text: str = ""
    costs_awarded: bool | None = None
    interest_text: str = ""
    sentence_text: str = ""
    relief_text: str = ""
    order_made: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PracticalOutcomeAssessment:
    outcomes: tuple[PracticalOutcome, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        return {"outcomes": [outcome.to_dict() for outcome in self.outcomes]}


def is_practical_outcome_prompt(prompt: str) -> bool:
    normalized = _normalize(prompt)
    cues = (
        "how much",
        "damages",
        "quantum",
        "costs",
        "interest",
        "relief",
        "order made",
        "orders made",
        "sentence",
        "what did they get",
        "what was awarded",
    )
    return any(cue in normalized for cue in cues)


def analyze_practical_outcomes(
    *,
    graph_evidence: list[dict[str, Any]] | None,
) -> PracticalOutcomeAssessment | None:
    outcomes: list[PracticalOutcome] = []
    for item in graph_evidence or []:
        reference = _text(item.get("reference") or item.get("citation") or item.get("title"))
        for raw in list(item.get("practical_outcomes") or []):
            if not isinstance(raw, dict):
                continue
            outcome = practical_outcome_from_mapping(raw, fallback_reference=reference)
            if outcome is not None:
                outcomes.append(outcome)
    if not outcomes:
        return None
    return PracticalOutcomeAssessment(outcomes=tuple(outcomes))


def practical_outcome_from_mapping(value: dict[str, Any], *, fallback_reference: str = "") -> PracticalOutcome | None:
    outcome = PracticalOutcome(
        reference=_text(value.get("reference") or fallback_reference),
        damages_awarded=_text(value.get("damages_awarded") or value.get("damages_text") or value.get("quantum")),
        costs_text=_text(value.get("costs_text")),
        costs_awarded=_bool_or_none(value.get("costs_awarded")),
        interest_text=_text(value.get("interest_text")),
        sentence_text=_text(value.get("sentence_text") or value.get("sentence")),
        relief_text=_text(value.get("relief_text") or value.get("relief_granted")),
        order_made=_text(value.get("order_made") or value.get("primary_order_text") or value.get("order")),
        confidence=max(0.0, min(1.0, float(value.get("confidence") or 0.0))),
    )
    if not any(
        (
            outcome.damages_awarded,
            outcome.costs_text,
            outcome.costs_awarded is not None,
            outcome.interest_text,
            outcome.sentence_text,
            outcome.relief_text,
            outcome.order_made,
        )
    ):
        return None
    return outcome


def render_practical_outcome_answer(assessment: PracticalOutcomeAssessment | None) -> str | None:
    if assessment is None or not assessment.outcomes:
        return None
    parts: list[str] = []
    for outcome in assessment.outcomes[:3]:
        label = outcome.reference or "Retrieved authority"
        details: list[str] = []
        if outcome.damages_awarded:
            details.append(f"damages/quantum: {outcome.damages_awarded}")
        if outcome.costs_text:
            details.append(f"costs: {outcome.costs_text}")
        elif outcome.costs_awarded is not None:
            details.append(f"costs awarded: {'yes' if outcome.costs_awarded else 'no'}")
        if outcome.interest_text:
            details.append(f"interest: {outcome.interest_text}")
        if outcome.relief_text:
            details.append(f"relief: {outcome.relief_text}")
        if outcome.order_made:
            details.append(f"order made: {outcome.order_made}")
        if outcome.sentence_text:
            details.append(f"sentence: {outcome.sentence_text}")
        parts.append(f"{label}: " + "; ".join(details))
    return "Practical litigation outcome: " + " | ".join(parts)


def render_practical_outcome_graph_lines(assessment: PracticalOutcomeAssessment | None) -> list[str]:
    if assessment is None or not assessment.outcomes:
        return []
    lines = ["  [PRACTICAL LITIGATION OUTCOME]"]
    for outcome in assessment.outcomes[:3]:
        if outcome.reference:
            lines.append(f"  Authority: {outcome.reference}")
        if outcome.damages_awarded:
            lines.append(f"  Damages/Quantum: {outcome.damages_awarded}")
        if outcome.costs_text:
            lines.append(f"  Costs: {outcome.costs_text}")
        elif outcome.costs_awarded is not None:
            lines.append(f"  Costs Awarded: {'yes' if outcome.costs_awarded else 'no'}")
        if outcome.interest_text:
            lines.append(f"  Interest: {outcome.interest_text}")
        if outcome.relief_text:
            lines.append(f"  Relief: {outcome.relief_text}")
        if outcome.order_made:
            lines.append(f"  Order Made: {outcome.order_made}")
        if outcome.sentence_text:
            lines.append(f"  Sentence: {outcome.sentence_text}")
    return lines


def load_practical_outcomes_for_documents(
    pipeline: Any,
    document_ids: list[str],
    *,
    limit_per_document: int = 2,
) -> dict[str, list[dict[str, Any]]]:
    normalized_ids = [str(item or "").strip() for item in document_ids if str(item or "").strip()]
    if not normalized_ids or not hasattr(pipeline, "store") or not hasattr(pipeline.store, "connect"):
        return {}
    placeholders = ",".join("?" for _ in normalized_ids)
    with pipeline.store.connect() as conn:
        try:
            rows = conn.execute(
                f"""
                SELECT
                    jm.document_id,
                    d.citation,
                    d.title,
                    jm.relief_text,
                    jm.costs_text,
                    jm.costs_awarded,
                    jm.primary_order_text,
                    jm.orders_json,
                    jm.structured_outcomes_json
                FROM document_judgment_metadata jm
                LEFT JOIN documents d ON d.id = jm.document_id
                WHERE jm.document_id IN ({placeholders})
                """,
                tuple(normalized_ids),
            ).fetchall()
        except Exception:
            return {}
    output: dict[str, list[dict[str, Any]]] = {document_id: [] for document_id in normalized_ids}
    for row in rows:
        document_id = _text(row["document_id"])
        entries = output.setdefault(document_id, [])
        if len(entries) >= limit_per_document:
            continue
        orders = _safe_json_list(row["orders_json"])
        structured = _safe_json_list(row["structured_outcomes_json"])
        damages_text = _extract_text_by_keys(structured, ("damages", "quantum", "compensation"))
        interest_text = _extract_text_by_keys(structured, ("interest",))
        sentence_text = _extract_text_by_keys(structured, ("sentence",))
        order_text = _text(row["primary_order_text"]) or _extract_text_by_keys(orders, ("text", "order", "order_text"))
        payload = {
            "reference": _text(row["citation"]) or _text(row["title"]) or document_id,
            "damages_awarded": damages_text,
            "costs_text": row["costs_text"],
            "costs_awarded": row["costs_awarded"],
            "interest_text": interest_text,
            "sentence_text": sentence_text,
            "relief_text": row["relief_text"],
            "order_made": order_text,
            "confidence": 0.78,
        }
        outcome = practical_outcome_from_mapping(payload)
        if outcome is not None:
            entries.append(outcome.to_dict())
    return {document_id: entries for document_id, entries in output.items() if entries}


def _safe_json_list(raw: object) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if not isinstance(raw, str) or not raw.strip():
        return []
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return [item for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _extract_text_by_keys(items: list[dict[str, Any]], keys: tuple[str, ...]) -> str:
    for item in items:
        haystack = _normalize(json.dumps(item, ensure_ascii=True))
        if not any(key in haystack for key in keys):
            continue
        for candidate_key in ("text", "amount", "value", "summary", "order", "relief"):
            value = _text(item.get(candidate_key))
            if value:
                return value
    return ""


def _bool_or_none(value: object) -> bool | None:
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    text = _normalize(value)
    if text in {"1", "true", "yes", "awarded"}:
        return True
    if text in {"0", "false", "no", "not awarded"}:
        return False
    return None


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _text(value: object) -> str:
    return str(value or "").strip()
