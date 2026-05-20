from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal


ElementStatus = Literal["satisfied", "failed", "insufficient_evidence"]


@dataclass(frozen=True, slots=True)
class ElementApplication:
    element: str
    status: ElementStatus
    material_fact: str
    evidence_source: str
    legal_consequence: str

    def to_dict(self) -> dict[str, str]:
        return asdict(self)

    def to_sentence(self) -> str:
        status_text = {
            "satisfied": "is satisfied",
            "failed": "fails",
            "insufficient_evidence": "has insufficient evidence",
        }[self.status]
        return (
            f"Element {self.element} {status_text} because {self.material_fact}. "
            f"Evidence source: {self.evidence_source}. "
            f"Legal consequence: {self.legal_consequence}"
        )


def build_element_applications(preferred: dict[str, Any]) -> list[ElementApplication]:
    item = dict(preferred.get("item") or {})
    test = dict(preferred.get("test") or {})
    reference = str(item.get("reference") or "retrieved authority").strip() or "retrieved authority"
    output: list[ElementApplication] = []
    for element in list(test.get("elements") or []):
        if not isinstance(element, dict):
            continue
        label = str(element.get("label") or "").strip()
        if not label:
            continue
        result = dict(element.get("result") or {})
        raw_status = str(result.get("status") or "").strip().lower()
        if raw_status == "satisfied":
            status: ElementStatus = "satisfied"
        elif raw_status == "failed":
            status = "failed"
        else:
            status = "insufficient_evidence"
        source_text = _first_non_empty(
            result.get("source_text"),
            result.get("fact"),
            result.get("finding"),
            element.get("source_text"),
            element.get("fact"),
        )
        material_fact = source_text or _default_material_fact(status)
        evidence_source = _first_non_empty(
            result.get("source_reference"),
            result.get("reference"),
            result.get("source_document_id"),
            item.get("document_id"),
            reference,
        )
        output.append(
            ElementApplication(
                element=label,
                status=status,
                material_fact=material_fact,
                evidence_source=evidence_source or reference,
                legal_consequence=_legal_consequence(status, label),
            )
        )
    return output


def has_failed_element(preferred: dict[str, Any] | None) -> bool:
    if not preferred:
        return False
    return any(item.status == "failed" for item in build_element_applications(preferred))


def render_element_application_summary(preferred: dict[str, Any], *, limit: int = 4) -> str:
    applications = build_element_applications(preferred)
    if not applications:
        return "Apply the retrieved legal test element by element and do not treat any missing element as proved without record support."
    sentences = [item.to_sentence() for item in applications[: max(1, int(limit))]]
    return "Apply the test element by element: " + " ".join(sentences)


def _first_non_empty(*values: object) -> str:
    for value in values:
        normalized = " ".join(str(value or "").split()).strip()
        if normalized:
            return normalized
    return ""


def _default_material_fact(status: ElementStatus) -> str:
    if status == "satisfied":
        return "the retrieved evidence supports the element"
    if status == "failed":
        return "the retrieved evidence does not prove the element"
    return "the retrieved record does not contain enough evidence to prove or disprove the element"


def _legal_consequence(status: ElementStatus, label: str) -> str:
    if status == "satisfied":
        return f"{label} may be treated as provisionally proved, subject to citation and record verification."
    if status == "failed":
        return f"the legal test is materially weakened unless {label} can be cured with stronger evidence or contrary authority."
    return f"do not treat {label} as established until the missing fact is supplied by verified authority or record evidence."

