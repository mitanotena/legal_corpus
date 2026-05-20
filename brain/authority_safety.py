from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class ObiterStatement:
    reference: str
    text: str
    source_paragraph: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class AuthoritySafetyAssessment:
    has_obiter: bool
    obiter_only: bool
    warning: str
    obiter_statements: tuple[ObiterStatement, ...] = field(default_factory=tuple)
    binding_statements: tuple[str, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["obiter_statements"] = [item.to_dict() for item in self.obiter_statements]
        payload["binding_statements"] = list(self.binding_statements)
        return payload


def analyze_authority_safety(
    *,
    graph_evidence: list[dict[str, Any]] | None,
) -> AuthoritySafetyAssessment | None:
    obiter: list[ObiterStatement] = []
    binding: list[str] = []
    seen_obiter: set[tuple[str, str]] = set()
    seen_binding: set[str] = set()

    for item in graph_evidence or []:
        reference = _text(item.get("reference") or item.get("citation") or item.get("title"))
        for statement in list(item.get("principle_statements") or []):
            if not isinstance(statement, dict):
                continue
            statement_type = _text(statement.get("statement_type")).lower()
            text = _text(statement.get("principle_text") or statement.get("text"))
            if not text:
                continue
            if statement_type == "obiter":
                key = (reference.lower(), text.lower())
                if key in seen_obiter:
                    continue
                seen_obiter.add(key)
                obiter.append(
                    ObiterStatement(
                        reference=reference,
                        text=text,
                        source_paragraph=_text(statement.get("source_paragraph")),
                        confidence=max(0.0, min(1.0, float(statement.get("confidence") or 0.0))),
                    )
                )
            elif statement_type in {"ratio", "holding", "rule"}:
                key = text.lower()
                if key in seen_binding:
                    continue
                seen_binding.add(key)
                binding.append(text)

    if not obiter:
        return None

    obiter_only = not binding
    if obiter_only:
        warning = (
            "The retrieved proposition is obiter only. Treat it as non-binding and persuasive only; "
            "it cannot satisfy citation verification as binding authority without a ratio or holding."
        )
    else:
        warning = (
            "Obiter appears in the retrieved material. It may inform the analysis, but the primary rule must come "
            "from the available ratio or holding, not from judicial commentary."
        )
    return AuthoritySafetyAssessment(
        has_obiter=True,
        obiter_only=obiter_only,
        warning=warning,
        obiter_statements=tuple(obiter),
        binding_statements=tuple(binding),
    )


def render_authority_safety_application(assessment: AuthoritySafetyAssessment | None) -> str | None:
    if assessment is None:
        return None
    if assessment.obiter_only:
        return (
            f"{assessment.warning} Do not state the obiter passage as the governing rule; "
            "use it only as supporting commentary after locating binding authority."
        )
    return assessment.warning


def render_authority_safety_graph_lines(assessment: AuthoritySafetyAssessment | None) -> list[str]:
    if assessment is None:
        return []
    lines = ["  [OBITER SAFETY WARNING]", f"  {assessment.warning}"]
    for statement in assessment.obiter_statements[:3]:
        reference = f"{statement.reference}: " if statement.reference else ""
        lines.append(f"  Obiter (non-binding, persuasive only): {reference}{statement.text}")
        if statement.source_paragraph:
            lines.append(f"    Source Paragraph: {statement.source_paragraph}")
    if assessment.binding_statements:
        lines.append(f"  Binding Ratio/Holding Available: {assessment.binding_statements[0]}")
    return lines


def _text(value: object) -> str:
    return str(value or "").strip()
