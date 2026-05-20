from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
import re
from typing import Any


class CourtRank(float, Enum):
    EACJ = 1.0
    SUPREME_COURT = 2.0
    COURT_OF_APPEAL = 3.0
    ZANZIBAR_COURT_OF_APPEAL = 3.5
    HIGH_COURT_INHERENT = 4.0
    HIGH_COURT_ORDINARY = 5.0
    DISTRICT_RESIDENT_MAGISTRATE = 6.0
    KADHI_COURT = 6.5
    PRIMARY_COURT = 7.0
    UNKNOWN = 99.0


class JurisdictionTrack(str, Enum):
    MAINLAND = "MAINLAND"
    ZANZIBAR = "ZANZIBAR"
    UNION_MATTER = "UNION_MATTER"
    EACJ_TREATY = "EACJ_TREATY"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class StareDecisisAssessment:
    has_guidance: bool
    controlling_reference: str
    controlling_court: str
    subordinate_reference: str
    subordinate_court: str
    conflict_type: str
    issue_text: str
    hierarchy_statement: str
    cross_track_warnings: tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["cross_track_warnings"] = list(self.cross_track_warnings)
        return payload


def analyze_stare_decisis(
    *,
    graph_evidence: list[dict[str, Any]] | None,
    prompt: str = "",
) -> StareDecisisAssessment | None:
    prompt_track = infer_jurisdiction_track(prompt)
    best: StareDecisisAssessment | None = None
    for item in graph_evidence or []:
        source_reference = _text(item.get("reference") or item.get("citation"))
        source_court = _text(item.get("court_level") or item.get("court") or item.get("normalized_court_level"))
        source_track = infer_jurisdiction_track(item.get("jurisdiction") or item.get("jurisdiction_track") or prompt)
        for alert in list(item.get("conflict_alerts") or []):
            if not isinstance(alert, dict):
                continue
            assessment = _assessment_from_alert(
                alert=alert,
                source_reference=source_reference,
                source_court=source_court,
                source_track=source_track,
                prompt_track=prompt_track,
            )
            if assessment is None:
                continue
            if best is None or assessment.confidence > best.confidence:
                best = assessment
    return best


def render_stare_decisis_graph_lines(assessment: StareDecisisAssessment | None) -> list[str]:
    if assessment is None or not assessment.has_guidance:
        return []
    lines = [
        "  [STARE DECISIS CONTROL]",
        f"  Controlling Authority: {assessment.controlling_reference} ({assessment.controlling_court})",
        f"  Subordinate Authority: {assessment.subordinate_reference} ({assessment.subordinate_court})",
        f"  Conflict Type: {assessment.conflict_type}",
        f"  Hierarchy: {assessment.hierarchy_statement}",
    ]
    if assessment.issue_text:
        lines.append(f"  Issue: {assessment.issue_text}")
    for warning in assessment.cross_track_warnings:
        lines.append(f"  Jurisdiction Warning: {warning}")
    return lines


def court_rank(value: object) -> CourtRank:
    raw = _normalize(value)
    if not raw:
        return CourtRank.UNKNOWN
    if "eacj" in raw or "east african court" in raw:
        return CourtRank.EACJ
    if "supreme" in raw:
        return CourtRank.SUPREME_COURT
    if "zanzibar" in raw and "court of appeal" in raw:
        return CourtRank.ZANZIBAR_COURT_OF_APPEAL
    if "court of appeal" in raw or "court_of_appeal" in raw or "tzca" in raw:
        return CourtRank.COURT_OF_APPEAL
    if "kadhi" in raw or "kadhi_court" in raw:
        return CourtRank.KADHI_COURT
    if "high court" in raw or "high_court" in raw or "tzhc" in raw:
        if "inherent" in raw:
            return CourtRank.HIGH_COURT_INHERENT
        return CourtRank.HIGH_COURT_ORDINARY
    if "district" in raw or "resident magistrate" in raw or "resident_magistrate" in raw:
        return CourtRank.DISTRICT_RESIDENT_MAGISTRATE
    if "primary" in raw:
        return CourtRank.PRIMARY_COURT
    return CourtRank.UNKNOWN


def infer_jurisdiction_track(value: object) -> JurisdictionTrack:
    raw = _normalize(value)
    if not raw:
        return JurisdictionTrack.UNKNOWN
    if "eacj" in raw or "east african" in raw or "treaty" in raw:
        return JurisdictionTrack.EACJ_TREATY
    if "zanzibar" in raw or "unguja" in raw or "pemba" in raw or "kadhi" in raw:
        return JurisdictionTrack.ZANZIBAR
    if "union" in raw or "constitution" in raw or "united republic" in raw:
        return JurisdictionTrack.UNION_MATTER
    if "mainland" in raw or "tanzania mainland" in raw or "tanganyika" in raw:
        return JurisdictionTrack.MAINLAND
    return JurisdictionTrack.UNKNOWN


def court_label(rank: CourtRank, fallback: str = "") -> str:
    labels = {
        CourtRank.EACJ: "EACJ",
        CourtRank.SUPREME_COURT: "Supreme Court",
        CourtRank.COURT_OF_APPEAL: "Court of Appeal",
        CourtRank.ZANZIBAR_COURT_OF_APPEAL: "Zanzibar Court of Appeal",
        CourtRank.HIGH_COURT_INHERENT: "High Court",
        CourtRank.HIGH_COURT_ORDINARY: "High Court",
        CourtRank.DISTRICT_RESIDENT_MAGISTRATE: "District/Resident Magistrate Court",
        CourtRank.KADHI_COURT: "Kadhi Court",
        CourtRank.PRIMARY_COURT: "Primary Court",
        CourtRank.UNKNOWN: fallback or "Unknown Court",
    }
    return labels[rank]


def _assessment_from_alert(
    *,
    alert: dict[str, Any],
    source_reference: str,
    source_court: str,
    source_track: JurisdictionTrack,
    prompt_track: JurisdictionTrack,
) -> StareDecisisAssessment | None:
    counterpart_reference = _text(alert.get("counterpart_reference") or alert.get("target_reference"))
    if not source_reference or not counterpart_reference:
        return None
    counterpart_court = _text(
        alert.get("counterpart_court_level")
        or alert.get("target_court_level")
        or alert.get("counterpart_court")
        or alert.get("court_level")
    )
    source_court = _text(alert.get("source_court_level") or alert.get("source_court") or source_court)
    source_rank = court_rank(source_court)
    counterpart_rank = court_rank(counterpart_court)
    if source_rank == CourtRank.UNKNOWN and counterpart_rank == CourtRank.UNKNOWN:
        return None
    if float(source_rank.value) <= float(counterpart_rank.value):
        controlling_reference = source_reference
        controlling_rank = source_rank
        controlling_track = source_track
        subordinate_reference = counterpart_reference
        subordinate_rank = counterpart_rank
        subordinate_court = counterpart_court
    else:
        controlling_reference = counterpart_reference
        controlling_rank = counterpart_rank
        controlling_track = infer_jurisdiction_track(
            alert.get("counterpart_jurisdiction")
            or alert.get("target_jurisdiction")
            or alert.get("jurisdiction")
            or counterpart_court
        )
        subordinate_reference = source_reference
        subordinate_rank = source_rank
        subordinate_court = source_court

    explicit = _text(alert.get("controlling_reference") or alert.get("controlling_case_reference"))
    if explicit:
        controlling_reference = explicit

    controlling_court = court_label(controlling_rank, _text(alert.get("controlling_court") or source_court or counterpart_court))
    subordinate_court_label = court_label(subordinate_rank, subordinate_court)
    issue_text = _text(alert.get("issue_text") or "the same legal issue")
    conflict_type = classify_conflict_type(alert)
    hierarchy_statement = _hierarchy_statement(
        controlling_court=controlling_court,
        subordinate_court=subordinate_court_label,
    )
    warnings = _cross_track_warnings(
        controlling_reference=controlling_reference,
        controlling_court=controlling_court,
        controlling_track=controlling_track,
        prompt_track=prompt_track,
    )
    confidence = float(alert.get("confidence") or 0.7)
    if explicit:
        confidence += 0.15
    if warnings:
        confidence -= 0.05
    return StareDecisisAssessment(
        has_guidance=True,
        controlling_reference=controlling_reference,
        controlling_court=controlling_court,
        subordinate_reference=subordinate_reference,
        subordinate_court=subordinate_court_label,
        conflict_type=conflict_type,
        issue_text=issue_text,
        hierarchy_statement=hierarchy_statement,
        cross_track_warnings=tuple(warnings),
        confidence=max(0.0, min(1.0, confidence)),
    )


def classify_conflict_type(alert: dict[str, Any]) -> str:
    raw = _normalize(
        alert.get("conflict_type")
        or alert.get("resolution_type")
        or alert.get("issue_text")
        or alert.get("review_note")
    )
    if any(token in raw for token in ("procedure", "procedural", "filing", "limitation", "jurisdiction", "leave")):
        return "procedural"
    if any(token in raw for token in ("fact", "evidence", "credibility", "witness", "proved")):
        return "factual"
    return "doctrinal"


def _hierarchy_statement(*, controlling_court: str, subordinate_court: str) -> str:
    if controlling_court == "Court of Appeal" and subordinate_court == "High Court":
        return "The High Court authority must yield to the Court of Appeal authority unless distinguishable."
    if controlling_court and subordinate_court:
        return f"The {subordinate_court} authority must yield to the {controlling_court} authority unless distinguishable or outside the same jurisdictional track."
    return "The lower authority must yield to the controlling higher authority unless distinguishable."


def _cross_track_warnings(
    *,
    controlling_reference: str,
    controlling_court: str,
    controlling_track: JurisdictionTrack,
    prompt_track: JurisdictionTrack,
) -> list[str]:
    if controlling_track in {JurisdictionTrack.UNKNOWN, JurisdictionTrack.UNION_MATTER}:
        return []
    if prompt_track in {JurisdictionTrack.UNKNOWN, JurisdictionTrack.UNION_MATTER, controlling_track}:
        return []
    if controlling_court == "Court of Appeal" and controlling_track == JurisdictionTrack.MAINLAND and prompt_track == JurisdictionTrack.ZANZIBAR:
        return [
            f"This Court of Appeal decision is from the Mainland track. Its application in Zanzibar requires separate analysis."
        ]
    return [
        f"{controlling_reference} appears to arise from the {controlling_track.value.replace('_', ' ').title()} track; applying it to the {prompt_track.value.replace('_', ' ').title()} track requires separate analysis."
    ]


def _text(value: object) -> str:
    return str(value or "").strip()


def _normalize(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "").replace("_", " ").strip().lower())
