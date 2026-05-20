from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Iterable


MAINLAND_ADVERSE_POSSESSION_YEARS = 12
INTERRUPTION_TYPES = {"court_case", "acknowledgment_of_title", "dispossession", "permission_granted"}


@dataclass(frozen=True)
class PossessionInterruption:
    date: date
    interruption_type: str
    description: str = ""
    source_reference: str | None = None


@dataclass(frozen=True)
class AdversePossessionFacts:
    jurisdiction: str
    possession_start: date
    assessment_date: date
    open_possession: bool
    continuous_possession: bool
    exclusive_possession: bool
    without_permission: bool
    interruptions: tuple[PossessionInterruption, ...] = ()


@dataclass(frozen=True)
class LegalTestElementResult:
    element_id: str
    label: str
    satisfied: bool
    reason: str


@dataclass(frozen=True)
class AdversePossessionResult:
    test_id: str
    jurisdiction: str
    satisfied: bool
    authority_safe: bool
    accrued_date: date | None
    years_required: int | None
    elements: tuple[LegalTestElementResult, ...]
    blocking_reasons: tuple[str, ...]


def parse_legal_date(value: str | date | datetime) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("date value is required")
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw).date()
    except ValueError as exc:
        raise ValueError(f"invalid ISO date: {value}") from exc


def add_years(value: date, years: int) -> date:
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def _normalize_jurisdiction(value: str) -> str:
    return str(value or "").strip().lower()


def _normalize_interruption_type(value: str) -> str:
    normalized = str(value or "").strip().lower().replace(" ", "_").replace("-", "_")
    return normalized


def _element(element_id: str, label: str, satisfied: bool, reason: str) -> LegalTestElementResult:
    return LegalTestElementResult(element_id=element_id, label=label, satisfied=bool(satisfied), reason=reason)


def evaluate_mainland_adverse_possession(facts: AdversePossessionFacts) -> AdversePossessionResult:
    jurisdiction = _normalize_jurisdiction(facts.jurisdiction)
    if jurisdiction != "mainland":
        return AdversePossessionResult(
            test_id="LegalTest:adverse_possession_mainland_12_years",
            jurisdiction=jurisdiction or "unknown",
            satisfied=False,
            authority_safe=False,
            accrued_date=None,
            years_required=None,
            elements=(),
            blocking_reasons=(f"Unsupported adverse-possession jurisdiction: {jurisdiction or 'unknown'}",),
        )

    accrued_date = add_years(facts.possession_start, MAINLAND_ADVERSE_POSSESSION_YEARS)
    temporal_satisfied = facts.assessment_date >= accrued_date
    interrupting_events = tuple(
        event
        for event in facts.interruptions
        if _normalize_interruption_type(event.interruption_type) in INTERRUPTION_TYPES
        and facts.possession_start <= event.date <= min(facts.assessment_date, accrued_date)
    )
    no_interruption = len(interrupting_events) == 0

    elements = (
        _element("ClaimElement:adverse_possession_open", "Open possession", facts.open_possession, "Possession must be visible or notorious."),
        _element(
            "ClaimElement:adverse_possession_continuous",
            "Continuous possession",
            facts.continuous_possession and no_interruption,
            "Possession must run continuously without a legally material interruption.",
        ),
        _element(
            "ClaimElement:adverse_possession_exclusive",
            "Exclusive possession",
            facts.exclusive_possession,
            "Possession must be exclusive against the paper owner and strangers.",
        ),
        _element(
            "ClaimElement:adverse_possession_without_permission",
            "Possession without permission",
            facts.without_permission,
            "Permissive occupation does not become adverse while permission continues.",
        ),
        _element(
            "ClaimElement:adverse_possession_12_year_gate",
            "Mainland 12-year temporal gate",
            temporal_satisfied and no_interruption,
            f"Mainland 12-year temporal gate requires possession until at least {accrued_date.isoformat()} without interruption.",
        ),
    )

    blocking_reasons: list[str] = [element.reason for element in elements if not element.satisfied]
    for event in interrupting_events:
        label = _normalize_interruption_type(event.interruption_type)
        blocking_reasons.append(f"Interrupted by {label} on {event.date.isoformat()}.")

    satisfied = all(element.satisfied for element in elements)
    return AdversePossessionResult(
        test_id="LegalTest:adverse_possession_mainland_12_years",
        jurisdiction="mainland",
        satisfied=satisfied,
        authority_safe=satisfied,
        accrued_date=accrued_date,
        years_required=MAINLAND_ADVERSE_POSSESSION_YEARS,
        elements=elements,
        blocking_reasons=tuple(blocking_reasons),
    )


def build_adverse_possession_facts(
    *,
    jurisdiction: str,
    possession_start: str | date | datetime,
    assessment_date: str | date | datetime,
    open_possession: bool,
    continuous_possession: bool,
    exclusive_possession: bool,
    without_permission: bool,
    interruptions: Iterable[dict[str, object] | PossessionInterruption] = (),
) -> AdversePossessionFacts:
    parsed_interruptions: list[PossessionInterruption] = []
    for event in interruptions:
        if isinstance(event, PossessionInterruption):
            parsed_interruptions.append(event)
            continue
        parsed_interruptions.append(
            PossessionInterruption(
                date=parse_legal_date(event.get("date")),
                interruption_type=str(event.get("interruption_type") or event.get("type") or ""),
                description=str(event.get("description") or ""),
                source_reference=str(event.get("source_reference") or "") or None,
            )
        )
    return AdversePossessionFacts(
        jurisdiction=jurisdiction,
        possession_start=parse_legal_date(possession_start),
        assessment_date=parse_legal_date(assessment_date),
        open_possession=bool(open_possession),
        continuous_possession=bool(continuous_possession),
        exclusive_possession=bool(exclusive_possession),
        without_permission=bool(without_permission),
        interruptions=tuple(parsed_interruptions),
    )
