from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


class BurdenCertaintyLevel(StrEnum):
    GRAPH_EVIDENCED = "GRAPH_EVIDENCED"
    JURISDICTIONAL_DEFAULT = "JURISDICTIONAL_DEFAULT"
    STATUTORY_IMPLICIT = "STATUTORY_IMPLICIT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class BurdenCertaintyAssessment:
    certainty: BurdenCertaintyLevel
    allocated_to: str
    standard_label: str
    source_text: str
    caveat: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["certainty"] = self.certainty.value
        return payload


UNKNOWN_BURDEN_ASSESSMENT = BurdenCertaintyAssessment(
    certainty=BurdenCertaintyLevel.UNKNOWN,
    allocated_to="",
    standard_label="",
    source_text="The retrieved corpus does not establish the burden or standard of proof.",
    caveat="Retrieve controlling primary authority before stating burden or standard conclusively.",
    confidence=0.0,
)


def assess_burden_certainty(
    *,
    prompt: str,
    preferred_burden: dict[str, Any] | None,
) -> BurdenCertaintyAssessment:
    if preferred_burden:
        burden = dict(preferred_burden.get("burden") or {})
        allocated_to = _normalize_party_role(burden.get("allocated_to"))
        standard_label = _clean(burden.get("standard_label"))
        source_text = _clean(burden.get("source_text"))
        confidence = _coerce_confidence(burden.get("confidence"))
        if allocated_to and allocated_to not in {"unknown", "unknown requires authority", "claimant or prosecution"}:
            return BurdenCertaintyAssessment(
                certainty=BurdenCertaintyLevel.GRAPH_EVIDENCED,
                allocated_to=allocated_to,
                standard_label=standard_label,
                source_text=source_text or "Burden allocation is supported by retrieved graph evidence.",
                caveat="Apply only to the issue and authority actually retrieved.",
                confidence=max(confidence, 0.5),
            )

    normalized_prompt = " ".join(str(prompt or "").lower().split())
    if _looks_criminal(normalized_prompt):
        return BurdenCertaintyAssessment(
            certainty=BurdenCertaintyLevel.JURISDICTIONAL_DEFAULT,
            allocated_to="prosecution",
            standard_label="beyond reasonable doubt",
            source_text=(
                "General Tanzanian criminal-law default: the accused is presumed innocent and the prosecution must prove guilt."
            ),
            caveat="This is a jurisdictional default; verify the specific offence, statute, and any reverse-onus provision.",
            confidence=0.72,
        )
    if _looks_statutory_offence(normalized_prompt):
        return BurdenCertaintyAssessment(
            certainty=BurdenCertaintyLevel.STATUTORY_IMPLICIT,
            allocated_to="prosecution",
            standard_label="beyond reasonable doubt",
            source_text="The query appears to concern a statutory offence, so prosecution burden is inferred only as a cautious default.",
            caveat="This is not a graph-extracted burden edge; verify the charging statute and any express allocation.",
            confidence=0.62,
        )
    if _looks_civil(normalized_prompt):
        return BurdenCertaintyAssessment(
            certainty=BurdenCertaintyLevel.JURISDICTIONAL_DEFAULT,
            allocated_to="claimant",
            standard_label="balance of probabilities",
            source_text="General civil-litigation default: the party asserting a claim must prove it on the balance of probabilities.",
            caveat="This is a general default; verify whether the governing statute, issue, or defence shifts the burden.",
            confidence=0.68,
        )
    return UNKNOWN_BURDEN_ASSESSMENT


def burden_rule_summary(assessment: BurdenCertaintyAssessment, *, reference: str = "") -> str:
    if assessment.certainty == BurdenCertaintyLevel.UNKNOWN:
        return "The retrieved corpus does not establish who bears the burden of proof or the applicable standard."
    prefix = f"{reference} indicates" if reference else "The burden assessment indicates"
    certainty_label = assessment.certainty.value.replace("_", " ").lower()
    standard = f" to the standard of {assessment.standard_label}" if assessment.standard_label else ""
    return (
        f"{prefix} that the burden rests on {assessment.allocated_to}{standard}. "
        f"Certainty: {certainty_label}. {assessment.caveat}"
    ).strip()


def burden_application_summary(assessment: BurdenCertaintyAssessment) -> str:
    if assessment.certainty == BurdenCertaintyLevel.UNKNOWN:
        return (
            "Do not state burden or standard conclusively. "
            "The retrieved corpus does not establish the burden of proof, so obtain controlling authority before advising."
        )
    return (
        f"Apply the burden cautiously against {assessment.allocated_to}. "
        f"Source basis: {assessment.source_text} "
        f"Caveat: {assessment.caveat}"
    ).strip()


def _clean(value: object) -> str:
    return " ".join(str(value or "").replace("_", " ").split()).strip()


def _normalize_party_role(value: object) -> str:
    return _clean(value).lower()


def _coerce_confidence(value: object) -> float:
    try:
        return max(0.0, min(1.0, float(value or 0.0)))
    except (TypeError, ValueError):
        return 0.0


def _looks_criminal(prompt: str) -> bool:
    cues = (
        "criminal",
        "accused",
        "prosecution",
        "charge",
        "charged",
        "offence",
        "offense",
        "conviction",
        "murder",
        "theft",
        "beyond reasonable doubt",
        "identification evidence",
    )
    return any(cue in prompt for cue in cues)


def _looks_statutory_offence(prompt: str) -> bool:
    return ("penal code" in prompt or "criminal procedure" in prompt) and ("section" in prompt or "cap" in prompt)


def _looks_civil(prompt: str) -> bool:
    cues = (
        "civil",
        "claimant",
        "plaintiff",
        "defendant",
        "contract",
        "tort",
        "land",
        "adverse possession",
        "injunction",
        "probabilities",
        "balance of probabilities",
    )
    return any(cue in prompt for cue in cues)

