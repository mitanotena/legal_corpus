from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from shared.legal_corpus.services.adverse_possession import (
    AdversePossessionFacts,
    AdversePossessionResult,
    build_adverse_possession_facts,
    evaluate_mainland_adverse_possession,
)


@dataclass(frozen=True)
class ClaimElementDefinition:
    element_id: str
    label: str
    sequence_no: int
    positive_phrases: tuple[str, ...]
    negative_phrases: tuple[str, ...] = ()
    temporal_gate: str | None = None


@dataclass(frozen=True)
class LegalTestDefinition:
    test_id: str
    label: str
    jurisdiction: str
    concept_id: str
    source_authority: str
    elements: tuple[ClaimElementDefinition, ...]
    trigger_phrases: tuple[str, ...]
    temporal_gate: str | None = None


@dataclass(frozen=True)
class ElementInference:
    element_id: str
    edge_type: str
    confidence: float
    source_excerpt: str
    reason: str
    review_status: str
    matched_phrase: str = ""


STANDARD_OF_PROOF_LABELS: dict[str, str] = {
    "beyond_reasonable_doubt": "Beyond reasonable doubt",
    "balance_of_probabilities": "Balance of probabilities",
    "preponderance_of_evidence": "Preponderance of evidence",
}


LEGAL_TEST_DEFINITIONS: tuple[LegalTestDefinition, ...] = (
    LegalTestDefinition(
        test_id="LegalTest:adverse_possession_mainland",
        label="Adverse possession Mainland test",
        jurisdiction="mainland",
        concept_id="LegalConcept:adverse_possession",
        source_authority="Law of Limitation Act, Cap. 89 (Mainland), applied through corpus-extracted case law",
        temporal_gate="mainland_12_years_without_effective_interruption",
        trigger_phrases=("adverse possession", "twelve years", "12 years", "limitation period", "open possession"),
        elements=(
            ClaimElementDefinition(
                element_id="ClaimElement:open_possession",
                label="Open possession",
                sequence_no=1,
                positive_phrases=("openly", "open possession", "visible possession", "notorious possession"),
                negative_phrases=("secret occupation", "concealed occupation"),
            ),
            ClaimElementDefinition(
                element_id="ClaimElement:continuous_possession",
                label="Continuous possession",
                sequence_no=2,
                positive_phrases=("continuous possession", "uninterrupted possession", "occupied continuously"),
                negative_phrases=("did not prove uninterrupted", "interrupted possession", "not continuous"),
            ),
            ClaimElementDefinition(
                element_id="ClaimElement:exclusive_possession",
                label="Exclusive possession",
                sequence_no=3,
                positive_phrases=("exclusive possession", "sole occupation", "occupied alone"),
                negative_phrases=("shared possession", "not exclusive"),
            ),
            ClaimElementDefinition(
                element_id="ClaimElement:possession_without_permission",
                label="Possession without permission",
                sequence_no=4,
                positive_phrases=("without permission", "without consent", "adverse to the owner", "hostile possession"),
                negative_phrases=("with permission", "permissive occupation", "licensee"),
            ),
            ClaimElementDefinition(
                element_id="ClaimElement:limitation_period_expired",
                label="Limitation period expired",
                sequence_no=5,
                positive_phrases=("twelve years", "12 years", "limitation period expired", "time barred"),
                negative_phrases=("before twelve years", "less than twelve years", "limitation period had not expired"),
                temporal_gate="mainland_12_years",
            ),
            ClaimElementDefinition(
                element_id="ClaimElement:no_effective_interruption",
                label="No effective interruption",
                sequence_no=6,
                positive_phrases=("without interruption", "uninterrupted", "no interruption"),
                negative_phrases=("interrupted", "acknowledgment of title", "acknowledgement of title", "suit filed", "dispossessed"),
                temporal_gate="no_court_case_acknowledgment_dispossession_or_permission",
            ),
        ),
    ),
    LegalTestDefinition(
        test_id="LegalTest:criminal_identification_evidence",
        label="Criminal identification evidence test",
        jurisdiction="union",
        concept_id="LegalConcept:identification_evidence",
        source_authority="Tanzania criminal case law on visual identification evidence",
        trigger_phrases=("identification", "watertight", "unfavourable conditions", "mistaken identity"),
        elements=(
            ClaimElementDefinition(
                "ClaimElement:favourable_identification_conditions",
                "Favourable identification conditions",
                1,
                (
                    "favourable conditions",
                    "favorable conditions",
                    "adequate light",
                    "sufficient light",
                    "very good circumstances",
                    "good circumstances",
                    "close distance",
                    "sufficient time",
                    "observed the appellant",
                    "saw the appellant",
                    "identified the appellant",
                    "identified him",
                    "identified her",
                ),
                ("unfavourable conditions", "unfavorable conditions", "poor light", "fleeting glance", "difficult conditions"),
            ),
            ClaimElementDefinition(
                "ClaimElement:witness_familiarity",
                "Witness familiarity",
                2,
                (
                    "known to the witness",
                    "recognized",
                    "recognised",
                    "familiar with",
                    "knew him",
                    "knew her",
                    "mentioned the name",
                    "mentioned his name",
                    "mentioned her name",
                    "identified by name",
                ),
                ("not known to the witness", "did not know"),
            ),
            ClaimElementDefinition(
                "ClaimElement:error_possibility_excluded",
                "Possibility of error excluded",
                3,
                (
                    "watertight",
                    "no possibility of mistaken identity",
                    "error excluded",
                    "proved beyond reasonable doubt",
                    "well founded",
                    "corroborate",
                    "corroborated",
                    "safe identification",
                    "properly identified",
                    "free from the possibility of error",
                    "free from possibility of error",
                    "safeguards against mistaken identity",
                    "unmistaken identification",
                ),
                ("possibility of error", "mistaken identity", "doubtful identification", "not watertight", "unsafe identification"),
            ),
        ),
    ),
    LegalTestDefinition(
        test_id="LegalTest:child_best_interests",
        label="Child custody best-interest test",
        jurisdiction="union",
        concept_id="LegalConcept:child_best_interests",
        source_authority="Law of the Child Act and Tanzania child welfare case law",
        trigger_phrases=("best interests of the child", "custody", "welfare of the child", "child welfare"),
        elements=(
            ClaimElementDefinition("ClaimElement:child_welfare", "Child welfare", 1, ("welfare of the child", "wellbeing", "best interests"), ()),
            ClaimElementDefinition("ClaimElement:parental_capacity", "Parental capacity", 2, ("parental capacity", "able to care", "stable home"), ("unable to care", "neglect")),
            ClaimElementDefinition("ClaimElement:child_views", "Child's views where appropriate", 3, ("child's wishes", "views of the child"), ()),
        ),
    ),
    LegalTestDefinition(
        test_id="LegalTest:winding_up_just_and_equitable",
        label="Just and equitable winding-up test",
        jurisdiction="union",
        concept_id="LegalConcept:winding_up",
        source_authority="Companies Act and Tanzania commercial case law",
        trigger_phrases=("winding up", "just and equitable", "deadlock", "breakdown of trust"),
        elements=(
            ClaimElementDefinition("ClaimElement:breakdown_of_trust", "Breakdown of trust", 1, ("breakdown of trust", "loss of confidence", "trust and confidence", "oppressive conduct"), ()),
            ClaimElementDefinition("ClaimElement:deadlock", "Corporate deadlock", 2, ("deadlock", "unable to manage", "management paralysis"), ()),
            ClaimElementDefinition("ClaimElement:last_resort", "Winding up as last resort", 3, ("last resort", "no alternative remedy", "cannot be allowed"), ("alternative remedy", "less drastic remedy", "prematurely invoke", "bypass these mechanisms")),
        ),
    ),
    LegalTestDefinition(
        test_id="LegalTest:contract_formation",
        label="Contract formation test",
        jurisdiction="union",
        concept_id="LegalConcept:contract_formation",
        source_authority="Law of Contract Act, Cap. 345",
        trigger_phrases=("contract", "offer", "acceptance", "consideration", "intention to create legal relations"),
        elements=(
            ClaimElementDefinition("ClaimElement:offer", "Offer", 1, ("offer", "proposal", "loan agreement", "lease"), ("no offer",)),
            ClaimElementDefinition("ClaimElement:acceptance", "Acceptance", 2, ("acceptance", "accepted", "executed", "signed"), ("no acceptance",)),
            ClaimElementDefinition("ClaimElement:consideration", "Consideration", 3, ("consideration", "valuable consideration", "loaned money", "credit facilities", "paid"), ("no consideration",)),
            ClaimElementDefinition("ClaimElement:intention_to_create_legal_relations", "Intention to create legal relations", 4, ("intention to create legal relations", "binding agreement", "liable to pay", "guarantors"), ()),
        ),
    ),
)

LAND_DOCTRINE_PRECEDENCE_PHRASES: tuple[str, ...] = (
    "land act",
    "village land act",
    "land division",
    "land case",
    "land appeal",
    "land application",
    "right of occupancy",
    "customary right of occupancy",
    "customary occupancy",
    "adverse possession",
    "district land and housing tribunal",
    "certificate of occupancy",
    "letter of offer",
    "unexhausted improvements",
    "village council",
)

EXPLICIT_CONTRACT_DISPUTE_PHRASES: tuple[str, ...] = (
    "breach of contract",
    "commercial case",
    "commercial division",
    "repayable loan",
    "loan agreement",
    "credit facilities",
    "guarantors",
    "guarantee agreement",
    "binding agreement",
    "intention to create legal relations",
)

CRIMINAL_PROCEDURE_MARKERS: tuple[str, ...] = (
    "criminal appeal",
    "criminal case",
    "accused",
    "prosecution",
    "beyond reasonable doubt",
    "identification parade",
    "mistaken identity",
    "robbery",
    "complainant",
)

CHILD_CUSTODY_MARKERS: tuple[str, ...] = (
    "best interests of the child",
    "welfare of the child",
    "child welfare",
    "minor child",
    "child custody",
    "custody of the child",
    "parental capacity",
)


def _normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def _document_family(text: str, concept_ids: Iterable[str]) -> str:
    lowered = _normalize_text(text)
    concept_text = " ".join(_normalize_text(item) for item in concept_ids if _normalize_text(item))
    merged = f"{lowered} {concept_text}".strip()
    if any(term in merged for term in ("criminal", "republic", "prosecution", "accused", "penal code")):
        return "criminal"
    if any(term in merged for term in ("land", "occupancy", "village land", "tribunal", "certificate of occupancy")):
        return "land"
    if any(term in merged for term in ("commercial", "company", "insolvency", "winding up", "shareholder")):
        return "commercial"
    if any(term in merged for term in ("labour", "labor", "employment", "employer", "employee", "cma")):
        return "labour"
    if any(term in merged for term in ("family", "custody", "maintenance", "child", "marriage")):
        return "family"
    if "civil" in merged:
        return "civil"
    return "unknown"


def iter_legal_test_definitions() -> Iterable[LegalTestDefinition]:
    return iter(LEGAL_TEST_DEFINITIONS)


def get_legal_test_definition(test_id: str) -> LegalTestDefinition | None:
    normalized = str(test_id or "").strip()
    for definition in LEGAL_TEST_DEFINITIONS:
        if definition.test_id == normalized:
            return definition
    return None


def detect_legal_tests(text: str, concept_ids: Iterable[str] = ()) -> list[LegalTestDefinition]:
    lowered = str(text or "").lower()
    concept_set = {str(concept_id or "").strip() for concept_id in concept_ids if str(concept_id or "").strip()}
    document_family = _document_family(lowered, concept_set)
    has_land_doctrine_context = any(phrase in lowered for phrase in LAND_DOCTRINE_PRECEDENCE_PHRASES)
    has_explicit_contract_dispute_context = any(phrase in lowered for phrase in EXPLICIT_CONTRACT_DISPUTE_PHRASES)
    has_criminal_context = any(phrase in lowered for phrase in CRIMINAL_PROCEDURE_MARKERS)
    has_child_custody_context = any(phrase in lowered for phrase in CHILD_CUSTODY_MARKERS)
    matches: list[LegalTestDefinition] = []
    for definition in LEGAL_TEST_DEFINITIONS:
        if definition.test_id == "LegalTest:contract_formation":
            if document_family not in {"civil", "commercial"}:
                continue
            if has_land_doctrine_context and not has_explicit_contract_dispute_context:
                continue
            if not has_explicit_contract_dispute_context:
                continue
        if definition.test_id == "LegalTest:criminal_identification_evidence":
            if document_family != "criminal" or not has_criminal_context:
                continue
        if definition.test_id == "LegalTest:child_best_interests":
            if document_family != "family" or not has_child_custody_context:
                continue
        if definition.test_id == "LegalTest:winding_up_just_and_equitable":
            if document_family != "commercial":
                continue
        if definition.test_id == "LegalTest:adverse_possession_mainland" and document_family not in {"land", "civil"}:
            continue
        if definition.concept_id in concept_set or any(phrase in lowered for phrase in definition.trigger_phrases):
            matches.append(definition)
    return matches


def standard_of_proof_id_from_text(text: str) -> str | None:
    lowered = str(text or "").lower()
    if "beyond reasonable doubt" in lowered:
        return "StandardOfProof:beyond_reasonable_doubt"
    if "balance of probabilities" in lowered:
        return "StandardOfProof:balance_of_probabilities"
    if "preponderance" in lowered:
        return "StandardOfProof:preponderance_of_evidence"
    return None


def standard_of_proof_label(standard_id: str) -> str:
    key = str(standard_id or "").split(":", 1)[-1]
    return STANDARD_OF_PROOF_LABELS.get(key, key.replace("_", " ").title())


def infer_element_mapping(element: ClaimElementDefinition, text: str) -> ElementInference | None:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return None
    lowered = normalized.lower()
    strong_positive_match = next(
        (
            phrase
            for phrase in element.positive_phrases
            if phrase in lowered
            and phrase
            in {
                "no possibility of mistaken identity",
                "free from the possibility of error",
                "free from possibility of error",
                "safeguards against mistaken identity",
                "unmistaken identification",
            }
        ),
        "",
    )
    if strong_positive_match:
        return ElementInference(
            element_id=element.element_id,
            edge_type="SATISFIES_ELEMENT",
            confidence=0.7,
            source_excerpt=normalized[:900],
            reason=f"Positive element phrase matched: {strong_positive_match}",
            review_status="needs_review",
            matched_phrase=strong_positive_match,
        )
    negative_match = next((phrase for phrase in element.negative_phrases if phrase in lowered), "")
    if negative_match:
        return ElementInference(
            element_id=element.element_id,
            edge_type="FAILS_ELEMENT",
            confidence=0.72,
            source_excerpt=normalized[:900],
            reason=f"Negative element phrase matched: {negative_match}",
            review_status="needs_review",
            matched_phrase=negative_match,
        )
    positive_match = next((phrase for phrase in element.positive_phrases if phrase in lowered), "")
    if positive_match:
        return ElementInference(
            element_id=element.element_id,
            edge_type="SATISFIES_ELEMENT",
            confidence=0.66,
            source_excerpt=normalized[:900],
            reason=f"Positive element phrase matched: {positive_match}",
            review_status="needs_review",
            matched_phrase=positive_match,
        )
    return None


def evaluate_adverse_possession_from_payload(
    *,
    jurisdiction: str,
    possession_start: str,
    assessment_date: str,
    open_possession: bool,
    continuous_possession: bool,
    exclusive_possession: bool,
    without_permission: bool,
    interruptions: Iterable[dict[str, object]] = (),
) -> AdversePossessionResult:
    facts: AdversePossessionFacts = build_adverse_possession_facts(
        jurisdiction=jurisdiction,
        possession_start=possession_start,
        assessment_date=assessment_date,
        open_possession=open_possession,
        continuous_possession=continuous_possession,
        exclusive_possession=exclusive_possession,
        without_permission=without_permission,
        interruptions=interruptions,
    )
    return evaluate_mainland_adverse_possession(facts)
