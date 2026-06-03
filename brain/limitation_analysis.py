# /** file limitation_analysis.py Limitation-period reasoning helpers for corpus-grounded legal synthesis [notes: avoids treating definitional adverse-possession prompts as limitation calculations without explicit time-bar cues] */

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, timedelta
import re
from typing import Any, Literal

from shared.legal_corpus.brain.statute_temporal import parse_iso_date


LimitationStatus = Literal["BARRED", "AT_RISK", "SAFE", "CANNOT_CONFIRM"]


@dataclass(frozen=True, slots=True)
class LimitationAnalysis:
    applicable_period_years: int | None
    applicable_period_label: str
    source: str
    accrual_date: str | None
    accrual_fact: str
    current_date: str | None
    expiry_date: str | None
    status: LimitationStatus
    tolling_factors: list[str] = field(default_factory=list)
    temporal_resolution: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    calculation: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def is_limitation_prompt(prompt: str) -> bool:
    normalized = " ".join(_client_query_text(prompt).lower().split())
    if not normalized:
        return False
    cues = (
        "limitation",
        "time barred",
        "time-barred",
        "barred by time",
        "out of time",
        "accrual",
        "twelve years",
        "12 years",
    )
    return any(cue in normalized for cue in cues)


def _client_query_text(prompt: str) -> str:
    """Extract the user-authored query from a structured synthesis prompt."""
    text = str(prompt or "")
    match = re.search(
        r"(?is)\bCLIENT QUERY:\s*(.*?)(?:\n\s*<retrieval_warnings>|\n\s*<private_document_sources>|\n\s*RETRIEVED |\n\s*REQUESTED ANSWER SHAPE:|\Z)",
        text,
    )
    if match:
        return match.group(1).strip()
    return text


def analyze_limitation(
    *,
    prompt: str,
    graph_evidence: list[dict[str, Any]] | None,
    current_date: str | None = None,
) -> LimitationAnalysis | None:
    evidence = _preferred_limitation_evidence(prompt=prompt, graph_evidence=graph_evidence)
    if evidence is None and not is_limitation_prompt(prompt):
        return None
    if evidence is None:
        return _cannot_confirm(
            current_date=current_date,
            caveats=[
                "No corpus-backed limitation period and no verified accrual date were supplied.",
                "Do not call the claim safe or barred until the governing limitation provision and accrual facts are retrieved.",
            ],
        )

    period_years = _int_or_none(
        evidence.get("applicable_period_years")
        or evidence.get("period_years")
        or evidence.get("limitation_years")
    )
    period_label = str(
        evidence.get("applicable_period_label")
        or evidence.get("period_label")
        or (f"{period_years} years" if period_years else "")
    ).strip()
    source = str(
        evidence.get("source")
        or evidence.get("source_reference")
        or evidence.get("source_text")
        or evidence.get("authority")
        or ""
    ).strip()
    accrual_date = _first_date_text(evidence.get("accrual_date") or evidence.get("breach_date") or evidence.get("cause_of_action_date"))
    accrual_fact = str(evidence.get("accrual_fact") or evidence.get("fact") or "").strip()
    resolved_current_date = _first_date_text(
        evidence.get("current_date")
        or evidence.get("as_of_date")
        or evidence.get("filing_date")
        or current_date
    )
    tolling_factors = _tolling_factors(evidence.get("tolling_factors") or evidence.get("interruptions") or [])
    temporal_resolution = _temporal_resolution(evidence)
    caveats: list[str] = []

    if not period_years:
        caveats.append("Applicable limitation period is missing or not numeric.")
    if not source:
        caveats.append("No primary source was supplied for the limitation period.")
    if not accrual_date:
        caveats.append("Accrual date is missing.")
    if not resolved_current_date:
        caveats.append("Current/filing date is missing.")
    if _date_uncertain(evidence, "accrual") or _date_uncertain(evidence, "current") or _date_uncertain(evidence, "filing"):
        caveats.append("One or more date fields are marked uncertain.")
    if tolling_factors:
        caveats.append("Potential tolling/interruption factors exist and must be resolved before a definitive limitation conclusion.")

    temporal_caveat = _temporal_caveat(temporal_resolution, accrual_date=accrual_date)
    if temporal_caveat:
        caveats.append(temporal_caveat)

    accrual = parse_iso_date(accrual_date)
    as_of = parse_iso_date(resolved_current_date)
    expiry = _add_years(accrual, period_years) if accrual and period_years else None
    if caveats or accrual is None or as_of is None or expiry is None:
        status: LimitationStatus = "CANNOT_CONFIRM"
    elif as_of > expiry:
        status = "BARRED"
    elif as_of >= expiry - timedelta(days=180):
        status = "AT_RISK"
    else:
        status = "SAFE"

    expiry_text = expiry.isoformat() if expiry else None
    calculation = _calculation_text(
        accrual_date=accrual_date,
        period_label=period_label or (f"{period_years} years" if period_years else "unknown"),
        current_date=resolved_current_date,
        expiry_date=expiry_text,
        status=status,
    )
    confidence = float(evidence.get("confidence") or 0.0)
    if status == "CANNOT_CONFIRM":
        confidence = min(confidence, 0.49)
    elif source and accrual_date and resolved_current_date:
        confidence = max(confidence, 0.75)

    return LimitationAnalysis(
        applicable_period_years=period_years,
        applicable_period_label=period_label or (f"{period_years} years" if period_years else "unknown"),
        source=source or "source not verified",
        accrual_date=accrual_date,
        accrual_fact=accrual_fact or "accrual fact not stated",
        current_date=resolved_current_date,
        expiry_date=expiry_text,
        status=status,
        tolling_factors=tolling_factors,
        temporal_resolution=temporal_resolution,
        caveats=_dedupe(caveats),
        calculation=calculation,
        confidence=confidence,
    )


def render_limitation_rule(analysis: LimitationAnalysis) -> str:
    if analysis.status == "CANNOT_CONFIRM":
        return (
            "A limitation conclusion requires a corpus-backed limitation period, a verified accrual date, "
            "and the limitation provision operative at accrual."
        )
    return (
        f"The applicable limitation period is {analysis.applicable_period_label}, sourced to {analysis.source}. "
        "Apply the version operative at accrual before stating whether the claim is time-barred."
    )


def render_limitation_application(analysis: LimitationAnalysis) -> str:
    lines = [analysis.calculation]
    if analysis.accrual_fact and analysis.accrual_fact != "accrual fact not stated":
        lines.append(f"Accrual fact: {analysis.accrual_fact}.")
    if analysis.temporal_resolution:
        operative_date = str(analysis.temporal_resolution.get("operative_date") or "").strip()
        resolution_basis = str(analysis.temporal_resolution.get("resolution_basis") or "").strip()
        scope = str(
            analysis.temporal_resolution.get("is_act_level_or_section_level")
            or analysis.temporal_resolution.get("commencement_scope")
            or ""
        ).strip()
        temporal_bits = [bit for bit in [f"operative date {operative_date}" if operative_date else "", resolution_basis, scope] if bit]
        if temporal_bits:
            lines.append("Temporal statute check: " + "; ".join(temporal_bits) + ".")
    for caveat in analysis.caveats[:3]:
        lines.append(f"Caveat: {caveat}")
    return " ".join(line.strip() for line in lines if line.strip())


def render_limitation_graph_lines(analysis: LimitationAnalysis) -> list[str]:
    lines = [
        f"  Limitation Calculation: {analysis.calculation}",
        f"    Source: {analysis.source}",
        f"    Accrual Fact: {analysis.accrual_fact}",
    ]
    if analysis.expiry_date:
        lines.append(f"    Expiry Date: {analysis.expiry_date}")
    if analysis.tolling_factors:
        lines.append("    Tolling/Interruption: " + "; ".join(analysis.tolling_factors[:3]))
    for caveat in analysis.caveats[:3]:
        lines.append(f"    Caveat: {caveat}")
    return lines


def _preferred_limitation_evidence(
    *,
    prompt: str,
    graph_evidence: list[dict[str, Any]] | None,
) -> dict[str, Any] | None:
    candidates: list[dict[str, Any]] = []
    for item in graph_evidence or []:
        reference = str(item.get("reference") or "").strip()
        for raw in _as_list(item.get("limitation_analyses") or item.get("limitation_analysis")):
            if isinstance(raw, dict):
                enriched = dict(raw)
                if reference and not enriched.get("source_reference"):
                    enriched["source_reference"] = reference
                candidates.append(enriched)
        for test in list(item.get("legal_tests") or []):
            if not isinstance(test, dict):
                continue
            inferred = _infer_from_legal_test(prompt=prompt, item=item, test=test)
            if inferred:
                candidates.append(inferred)
    if not candidates:
        return None
    return sorted(candidates, key=_limitation_score, reverse=True)[0]


def _infer_from_legal_test(*, prompt: str, item: dict[str, Any], test: dict[str, Any]) -> dict[str, Any] | None:
    label = str(test.get("label") or "").lower()
    temporal_gate = str(test.get("temporal_gate") or "").lower()
    haystack = f"{label} {temporal_gate} {prompt}".lower()
    period_years = _period_years_from_text(haystack)
    if period_years is None:
        return None
    accrual_date = _first_date_text(prompt)
    return {
        "applicable_period_years": period_years,
        "applicable_period_label": f"{period_years} years",
        "source": str(test.get("source_authority") or item.get("reference") or "").strip(),
        "accrual_date": accrual_date,
        "current_date": None,
        "accrual_fact": "Date inferred from counsel's prompt; verify pleadings and evidence.",
        "confidence": float(test.get("confidence") or 0.55),
    }


def _limitation_score(item: dict[str, Any]) -> float:
    score = float(item.get("confidence") or 0.0)
    if _int_or_none(item.get("applicable_period_years") or item.get("period_years") or item.get("limitation_years")):
        score += 2.0
    if _first_date_text(item.get("accrual_date") or item.get("breach_date") or item.get("cause_of_action_date")):
        score += 2.0
    if _first_date_text(item.get("current_date") or item.get("as_of_date") or item.get("filing_date")):
        score += 1.0
    if item.get("source") or item.get("source_reference") or item.get("source_text"):
        score += 1.0
    return score


def _cannot_confirm(*, current_date: str | None, caveats: list[str]) -> LimitationAnalysis:
    resolved_current_date = _first_date_text(current_date)
    return LimitationAnalysis(
        applicable_period_years=None,
        applicable_period_label="unknown",
        source="source not verified",
        accrual_date=None,
        accrual_fact="accrual fact not stated",
        current_date=resolved_current_date,
        expiry_date=None,
        status="CANNOT_CONFIRM",
        caveats=_dedupe(caveats),
        calculation=_calculation_text(
            accrual_date=None,
            period_label="unknown",
            current_date=resolved_current_date,
            expiry_date=None,
            status="CANNOT_CONFIRM",
        ),
        confidence=0.0,
    )


def _temporal_resolution(evidence: dict[str, Any]) -> dict[str, Any]:
    raw = evidence.get("temporal_resolution") or evidence.get("statute_temporal") or evidence.get("operative_section_version")
    return dict(raw) if isinstance(raw, dict) else {}


def _temporal_caveat(temporal_resolution: dict[str, Any], *, accrual_date: str | None) -> str | None:
    if not temporal_resolution:
        return "No temporal statute resolution proves the limitation provision was operative at accrual."
    scope = str(
        temporal_resolution.get("is_act_level_or_section_level")
        or temporal_resolution.get("commencement_scope")
        or ""
    ).strip()
    if scope == "act_level_unverified" or temporal_resolution.get("commencement_warning"):
        return "Only Act-level commencement is available; section-specific commencement at accrual is not verified."
    accrual = parse_iso_date(accrual_date)
    valid_from = parse_iso_date(temporal_resolution.get("valid_from"))
    valid_to = parse_iso_date(temporal_resolution.get("valid_to"))
    if accrual is None:
        return None
    starts = valid_from is None or valid_from <= accrual
    ends = valid_to is None or accrual < valid_to
    if not (starts and ends):
        return "The selected limitation provision version does not cover the pleaded accrual date."
    return None


def _date_uncertain(evidence: dict[str, Any], prefix: str) -> bool:
    keys = (
        f"{prefix}_date_uncertain",
        f"{prefix}_date_estimated",
        f"{prefix}_date_verified",
    )
    for key in keys:
        if key.endswith("_verified") and key in evidence:
            return not bool(evidence.get(key))
        if key in evidence and bool(evidence.get(key)):
            return True
    quality = str(evidence.get(f"{prefix}_date_quality") or "").strip().lower()
    return quality in {"uncertain", "estimated", "approximate", "unknown"}


def _period_years_from_text(text: str) -> int | None:
    normalized = str(text or "").lower()
    match = re.search(r"\b(\d{1,2})\s*(?:year|years|yr|yrs)\b", normalized)
    if match:
        return _int_or_none(match.group(1))
    if "twelve year" in normalized or "twelve years" in normalized:
        return 12
    return None


def _first_date_text(value: object) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    parsed = parse_iso_date(text)
    if parsed:
        return parsed.isoformat()
    match = re.search(r"\b(19|20)\d{2}-\d{2}-\d{2}\b", text)
    if match:
        return match.group(0)
    return None


def _add_years(value: date, years: int | None) -> date | None:
    if years is None:
        return None
    try:
        return value.replace(year=value.year + years)
    except ValueError:
        return value.replace(month=2, day=28, year=value.year + years)


def _calculation_text(
    *,
    accrual_date: str | None,
    period_label: str,
    current_date: str | None,
    expiry_date: str | None,
    status: LimitationStatus,
) -> str:
    return (
        f"Accrual: {accrual_date or 'UNKNOWN'}. "
        f"Limitation: {period_label or 'UNKNOWN'}. "
        f"Current date: {current_date or 'UNKNOWN'}. "
        f"Expiry: {expiry_date or 'UNKNOWN'}. "
        f"Status: {status}."
    )


def _tolling_factors(raw: object) -> list[str]:
    factors: list[str] = []
    for item in _as_list(raw):
        if isinstance(item, dict):
            label = str(item.get("description") or item.get("type") or item.get("label") or "").strip()
            item_date = _first_date_text(item.get("date") or item.get("event_date"))
            if label and item_date:
                factors.append(f"{label} on {item_date}")
            elif label:
                factors.append(label)
        else:
            text = str(item or "").strip()
            if text:
                factors.append(text)
    return _dedupe(factors)


def _as_list(value: object) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _int_or_none(value: object) -> int | None:
    try:
        parsed = int(str(value or "").strip())
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _dedupe(values: list[str]) -> list[str]:
    output: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = " ".join(str(value or "").split()).strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output
