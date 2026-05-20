from __future__ import annotations

import json
import re
from typing import Any, Iterable

from shared.legal_corpus.crawler.legal_concepts import iter_legal_concept_seeds
from shared.legal_corpus.crawler.legal_tests import (
    ClaimElementDefinition,
    LegalTestDefinition,
    detect_legal_tests,
    get_legal_test_definition,
    infer_element_mapping,
    iter_legal_test_definitions,
    standard_of_proof_id_from_text,
    standard_of_proof_label,
)
from shared.legal_corpus.crawler.ontology import ONTOLOGY_VERSION
from shared.legal_corpus.crawler.utils import sha256_text


CONCEPT_SEED_BY_ID = {seed.concept_id: seed for seed in iter_legal_concept_seeds()}
STRICT_PAYLOAD_TEST_IDS = {
    "LegalTest:contract_formation",
    "LegalTest:criminal_identification_evidence",
    "LegalTest:child_best_interests",
    "LegalTest:winding_up_just_and_equitable",
    "LegalTest:adverse_possession_mainland",
}


def normalize_text(value: object) -> str:
    return " ".join(str(value or "").strip().lower().split())


def infer_document_family(*, title: str, context_text: str, doctrine_areas: Iterable[str]) -> str:
    merged = " ".join(
        [
            normalize_text(title),
            normalize_text(context_text),
            " ".join(normalize_text(area) for area in doctrine_areas if normalize_text(area)),
        ]
    ).strip()
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


def explicit_contract_dispute_context(text: str) -> bool:
    lowered = normalize_text(text)
    phrases = (
        "breach of contract",
        "offer and acceptance",
        "intention to create legal relations",
        "valuable consideration",
        "binding agreement",
        "lease agreement",
        "loan agreement",
        "guarantee agreement",
        "credit facilities",
        "repayable loan",
    )
    return any(phrase in lowered for phrase in phrases)


def payload_test_allowed(
    *,
    definition: LegalTestDefinition,
    detected_test_ids: set[str],
    document_family: str,
    context_text: str,
) -> bool:
    if definition.test_id not in STRICT_PAYLOAD_TEST_IDS:
        return True
    if definition.test_id in detected_test_ids:
        return True
    if definition.test_id == "LegalTest:contract_formation":
        return document_family in {"civil", "commercial"} and explicit_contract_dispute_context(context_text)
    if definition.test_id == "LegalTest:criminal_identification_evidence":
        return document_family == "criminal"
    if definition.test_id == "LegalTest:child_best_interests":
        return document_family == "family"
    if definition.test_id == "LegalTest:winding_up_just_and_equitable":
        return document_family == "commercial" and (
            "winding up" in normalize_text(context_text) or "just and equitable" in normalize_text(context_text)
        )
    if definition.test_id == "LegalTest:adverse_possession_mainland":
        return document_family == "land"
    return False


def safe_json_list(raw_value: object) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        return [item for item in raw_value if isinstance(item, dict)]
    if not isinstance(raw_value, str) or not raw_value.strip():
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [item for item in parsed if isinstance(item, dict)]


def safe_json_dict(raw_value: object) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return dict(raw_value)
    if not isinstance(raw_value, str) or not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def item_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(item.get(key) or "").strip()
        if value:
            return value
    return ""


def node_id(node_type: str, document_id: str, index: int) -> str:
    return f"{node_type}:{document_id}:{index}"


def concept_ids_from_text(*values: object) -> list[str]:
    text = " ".join(str(value or "") for value in values).lower()
    seen: set[str] = set()
    concept_ids: list[str] = []
    for seed in iter_legal_concept_seeds():
        phrases = (seed.pref_label_en, *seed.aliases)
        if not any(str(phrase or "").lower() in text for phrase in phrases):
            continue
        if seed.concept_id in seen:
            continue
        concept_ids.append(seed.concept_id)
        seen.add(seed.concept_id)
    return concept_ids


def merge_concept_ids(*groups: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    merged: list[str] = []
    for group in groups:
        for item in group:
            normalized = str(item or "").strip()
            if not normalized or normalized in seen:
                continue
            merged.append(normalized)
            seen.add(normalized)
    return merged


def collect_payload_context(
    *,
    title: str,
    facts: list[dict[str, Any]],
    issues: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    ratios: list[dict[str, Any]],
    burdens: list[dict[str, Any]],
    outcomes: list[dict[str, Any]],
) -> str:
    chunks: list[str] = [title]
    chunks.extend(item_text(item, "text", "issue_text", "holding_text", "quote", "primary_order_text") for item in facts)
    chunks.extend(item_text(item, "issue_text", "text") for item in issues)
    chunks.extend(item_text(item, "holding_text", "text") for item in holdings)
    chunks.extend(item_text(item, "quote", "text", "interpretation") for item in ratios)
    chunks.extend(item_text(item, "text") for item in burdens)
    chunks.extend(item_text(item, "primary_order_text", "outcome_type", "text") for item in outcomes)
    return " ".join(chunk for chunk in chunks if chunk)


def legal_tests_from_payload(
    *,
    title: str,
    payload_tests: list[dict[str, Any]],
    context_text: str,
    concept_ids: Iterable[str],
) -> list[LegalTestDefinition]:
    concept_id_list = [str(item or "").strip() for item in concept_ids if str(item or "").strip()]
    document_doctrine_areas = {
        str(seed.doctrine_area or "").strip()
        for concept_id in concept_id_list
        for seed in [CONCEPT_SEED_BY_ID.get(concept_id)]
        if seed is not None and str(seed.doctrine_area or "").strip()
    }
    detected_tests = detect_legal_tests(context_text, concept_id_list)
    detected_test_ids = {definition.test_id for definition in detected_tests}
    document_family = infer_document_family(
        title=title,
        context_text=context_text,
        doctrine_areas=document_doctrine_areas,
    )
    definitions: list[LegalTestDefinition] = []
    seen: set[str] = set()
    for item in payload_tests:
        test_id = str(item.get("test_id") or "").strip()
        definition = get_legal_test_definition(test_id)
        if definition is None:
            continue
        concept_seed = CONCEPT_SEED_BY_ID.get(definition.concept_id)
        test_doctrine_area = str(concept_seed.doctrine_area or "").strip() if concept_seed is not None else ""
        if document_doctrine_areas and test_doctrine_area and test_doctrine_area not in document_doctrine_areas:
            continue
        if not payload_test_allowed(
            definition=definition,
            detected_test_ids=detected_test_ids,
            document_family=document_family,
            context_text=context_text,
        ):
            continue
        definitions.append(definition)
        seen.add(definition.test_id)
    for definition in detected_tests:
        if definition.test_id in seen:
            continue
        definitions.append(definition)
        seen.add(definition.test_id)
    return definitions


def definition_for_element(element_id: str, tests: Iterable[LegalTestDefinition]) -> ClaimElementDefinition | None:
    normalized = str(element_id or "").strip()
    for test in tests:
        for element in test.elements:
            if element.element_id == normalized:
                return element
    for test in iter_legal_test_definitions():
        for element in test.elements:
            if element.element_id == normalized:
                return element
    return None


def source_for_test(document_id: str, holdings: list[dict[str, Any]], ratios: list[dict[str, Any]]) -> tuple[str, str, dict[str, Any]]:
    if holdings:
        text = item_text(holdings[0], "holding_text", "text")
        return node_id("Holding", document_id, 0), "Holding", {"text": text, "segment_index": 0}
    if ratios:
        text = item_text(ratios[0], "quote", "text")
        return node_id("Ratio", document_id, 0), "Ratio", {"text": text, "segment_index": 0}
    return f"Case:{document_id}", "Case", {"canonical_id": document_id}


def source_for_element_candidate(
    *,
    document_id: str,
    candidate: dict[str, Any],
    facts: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
) -> tuple[str, str, str, int | None]:
    fact_indexes = candidate.get("supporting_fact_indexes")
    if isinstance(fact_indexes, list):
        for raw_index in fact_indexes:
            if isinstance(raw_index, int) and 0 <= raw_index < len(facts):
                return node_id("Fact", document_id, raw_index), "Fact", item_text(facts[raw_index], "text"), raw_index
    holding_index = candidate.get("linked_holding_index")
    if isinstance(holding_index, int) and 0 <= holding_index < len(holdings):
        return node_id("Holding", document_id, holding_index), "Holding", item_text(holdings[holding_index], "holding_text", "text"), holding_index
    if holdings:
        return node_id("Holding", document_id, 0), "Holding", item_text(holdings[0], "holding_text", "text"), 0
    if facts:
        return node_id("Fact", document_id, 0), "Fact", item_text(facts[0], "text"), 0
    return f"Holding:{document_id}:0", "Holding", "", None


def evidence_items_for_element(
    *,
    facts: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    ratios: list[dict[str, Any]],
    burdens: list[dict[str, Any]],
) -> list[tuple[str, int, str]]:
    items: list[tuple[str, int, str]] = []
    for index, item in enumerate(facts):
        text = item_text(item, "text")
        if text:
            items.append(("Fact", index, text))
    for index, item in enumerate(holdings):
        text = item_text(item, "holding_text", "text")
        if text:
            items.append(("Holding", index, text))
    for index, item in enumerate(ratios):
        text = item_text(item, "quote", "text", "interpretation")
        if text:
            items.append(("Holding", min(index, max(0, len(holdings) - 1)), text))
    for index, item in enumerate(burdens):
        text = item_text(item, "text")
        if text:
            items.append(("Holding", min(index, max(0, len(holdings) - 1)), text))
    return items


def source_for_inferred_element(
    *,
    document_id: str,
    element: ClaimElementDefinition,
    facts: list[dict[str, Any]],
    holdings: list[dict[str, Any]],
    ratios: list[dict[str, Any]],
    burdens: list[dict[str, Any]],
    context_text: str,
) -> tuple[str, str, str, int | None, Any | None]:
    best: tuple[str, int, str, Any] | None = None
    for source_type, index, text in evidence_items_for_element(facts=facts, holdings=holdings, ratios=ratios, burdens=burdens):
        inference = infer_element_mapping(element, text)
        if inference is None:
            continue
        if best is None or inference.confidence > best[3].confidence:
            best = (source_type, index, text, inference)
    if best is not None:
        source_type, index, text, inference = best
        return node_id(source_type, document_id, index), source_type, text, index, inference
    inference = infer_element_mapping(element, context_text)
    if inference is not None:
        if holdings:
            return node_id("Holding", document_id, 0), "Holding", item_text(holdings[0], "holding_text", "text"), 0, inference
        if facts:
            return node_id("Fact", document_id, 0), "Fact", item_text(facts[0], "text"), 0, inference
        return f"Holding:{document_id}:0", "Holding", context_text[:900], None, inference
    return f"Holding:{document_id}:0", "Holding", "", None, None


def fallback_review_mapping_for_test(
    *,
    test: LegalTestDefinition,
    context_text: str,
) -> tuple[ClaimElementDefinition, str, float]:
    lowered = context_text.lower()
    if "dismiss" in lowered or "not prove" in lowered or "failed" in lowered or "weak" in lowered:
        return test.elements[-1], "failed", 0.5
    if "allowed" in lowered or "proved" in lowered or "well founded" in lowered or "liable" in lowered:
        return test.elements[0], "satisfied", 0.5
    return test.elements[0], "needs_review", 0.45


def upsert_edge_counted(
    *,
    store: Any,
    counts: dict[str, int],
    count_key: str,
    edge_type: str,
    source_node_id: str,
    source_node_type: str,
    target_node_id: str,
    target_node_type: str,
    confidence: float,
    status: str,
    provenance: dict[str, Any],
    evidence: dict[str, Any],
) -> None:
    result = store.upsert_legal_edge(
        edge_type=edge_type,
        source_node_id=source_node_id,
        source_node_type=source_node_type,
        target_node_id=target_node_id,
        target_node_type=target_node_type,
        confidence=confidence,
        status=status,
        provenance=provenance,
        evidence=evidence,
    )
    if result.get("status") in {"active", "needs_review"}:
        counts[count_key] = counts.get(count_key, 0) + 1
    if result.get("status") == "needs_review":
        counts["needsReviewEdges"] = counts.get("needsReviewEdges", 0) + 1


def materialize_document_element_mapping(
    *,
    store: Any,
    row: Any,
    counts: dict[str, int],
    mode: str,
) -> None:
    document_id = str(row["id"])
    title = str(row["title"] or "")
    jurisdiction = str(row["jurisdiction"] or "")
    issues = safe_json_list(row["issues_framed_json"])
    holdings = safe_json_list(row["holdings_json"])
    ratios = safe_json_list(row["ratio_segments_json"])
    facts = safe_json_list(row["fact_points_json"])
    outcomes = safe_json_list(row["structured_outcomes_json"])
    burdens = safe_json_list(row["deontic_annotations_json"])
    metadata = safe_json_dict(row["metadata_json"])
    raw_payload = safe_json_dict(metadata.get("master_extraction_payload"))
    payload_tests = safe_json_list(raw_payload.get("legal_tests"))
    payload_candidates = safe_json_list(raw_payload.get("element_candidates"))
    context_text = collect_payload_context(
        title=title,
        facts=facts,
        issues=issues,
        holdings=holdings,
        ratios=ratios,
        burdens=burdens,
        outcomes=outcomes,
    )
    concept_ids = merge_concept_ids(
        concept_ids_from_text(context_text),
        *(item.get("legal_concepts") or [] for item in [*issues, *ratios] if isinstance(item.get("legal_concepts"), list)),
    )
    tests = legal_tests_from_payload(
        title=title,
        payload_tests=payload_tests,
        context_text=context_text,
        concept_ids=concept_ids,
    )
    if not tests:
        return

    source_properties = {
        "document_id": document_id,
        "title": title,
        "document_type": str(row["document_type"] or "judgment"),
        "jurisdiction": jurisdiction,
        "language": str(row["language"] or "EN").upper(),
    }
    base_provenance = {
        "source": "element_materializer",
        "source_document_id": document_id,
        "ontology_version": ONTOLOGY_VERSION,
        "extraction_schema_version": metadata.get("extraction_schema_version"),
        "static_prompt_hash": metadata.get("static_prompt_hash"),
        "ontology_context_hash": metadata.get("ontology_context_hash"),
        "source_text_hash": metadata.get("source_text_hash"),
        "authority_safe": False,
        "validation_status": "materialized",
        "source_properties": source_properties,
    }
    test_source_id, test_source_type, test_source_properties = source_for_test(document_id, holdings, ratios)

    for test in tests:
        matched_payload = next((item for item in payload_tests if str(item.get("test_id") or "").strip() == test.test_id), {})
        test_confidence = float(matched_payload.get("confidence") or 0.64)
        upsert_edge_counted(
            store=store,
            counts=counts,
            count_key="appliesTestEdges",
            edge_type="APPLIES_TEST",
            source_node_id=test_source_id,
            source_node_type=test_source_type,
            target_node_id=test.test_id,
            target_node_type="LegalTest",
            confidence=test_confidence,
            status="active" if test_confidence >= 0.6 else "needs_review",
            provenance={
                **base_provenance,
                "source_properties": {**source_properties, **test_source_properties},
                "target_properties": {
                    "test_id": test.test_id,
                    "label": test.label,
                    "jurisdiction": test.jurisdiction,
                    "concept_id": test.concept_id,
                    "source_authority": test.source_authority,
                    "temporal_gate": test.temporal_gate,
                },
            },
            evidence={
                "test_id": test.test_id,
                "label": test.label,
                "legal_concept_id": test.concept_id,
                "confidence": test_confidence,
                "source_document_id": document_id,
            },
        )
        for element in test.elements:
            upsert_edge_counted(
                store=store,
                counts=counts,
                count_key="hasElementEdges",
                edge_type="HAS_ELEMENT",
                source_node_id=test.test_id,
                source_node_type="LegalTest",
                target_node_id=element.element_id,
                target_node_type="ClaimElement",
                confidence=1.0,
                status="active",
                provenance={
                    **base_provenance,
                    "source": "legal_test_catalogue",
                    "source_properties": {
                        "test_id": test.test_id,
                        "label": test.label,
                        "jurisdiction": test.jurisdiction,
                    },
                    "target_properties": {
                        "element_id": element.element_id,
                        "label": element.label,
                        "sequence_no": element.sequence_no,
                        "temporal_gate": element.temporal_gate,
                    },
                },
                evidence={
                    "sequence_no": element.sequence_no,
                    "temporal_gate": element.temporal_gate,
                    "source_document_id": document_id,
                },
            )

    candidates_by_element: dict[str, list[dict[str, Any]]] = {}
    for candidate in payload_candidates:
        element_id = str(candidate.get("element_id") or "").strip()
        if not element_id:
            continue
        candidates_by_element.setdefault(element_id, []).append(candidate)

    for test in tests:
        produced_element_outcome = False
        for element in test.elements:
            candidate_items = candidates_by_element.get(element.element_id, [])
            if not candidate_items:
                source_id, source_type, source_text, source_index, inference = source_for_inferred_element(
                    document_id=document_id,
                    element=element,
                    facts=facts,
                    holdings=holdings,
                    ratios=ratios,
                    burdens=burdens,
                    context_text=context_text,
                )
                if inference is None:
                    continue
                candidate_items = [
                    {
                        "element_id": element.element_id,
                        "linked_holding_index": source_index if source_type == "Holding" else (0 if holdings else None),
                        "supporting_fact_indexes": [source_index] if source_type == "Fact" and source_index is not None else [],
                        "candidate_outcome": "satisfied" if inference.edge_type == "SATISFIES_ELEMENT" else "failed",
                        "confidence": inference.confidence,
                        "source_paragraph": "deterministic_context",
                        "materializer_reason": inference.reason,
                        "_source_node_id": source_id,
                        "_source_node_type": source_type,
                        "_source_text": source_text,
                        "_source_index": source_index,
                        "_inference": inference,
                    }
                ]
            for candidate in candidate_items:
                definition = definition_for_element(str(candidate.get("element_id") or ""), tests)
                if definition is None:
                    continue
                if candidate.get("_source_node_id"):
                    source_id = str(candidate["_source_node_id"])
                    source_type = str(candidate["_source_node_type"])
                    source_text = str(candidate.get("_source_text") or "")
                    source_index = candidate.get("_source_index") if isinstance(candidate.get("_source_index"), int) else None
                    inference = candidate.get("_inference")
                else:
                    source_id, source_type, source_text, source_index = source_for_element_candidate(
                        document_id=document_id,
                        candidate=candidate,
                        facts=facts,
                        holdings=holdings,
                    )
                    inference = infer_element_mapping(definition, " ".join([source_text, context_text]))
                raw_outcome = str(candidate.get("candidate_outcome") or "").strip().lower()
                edge_type = "SATISFIES_ELEMENT"
                confidence = float(candidate.get("confidence") or 0.52)
                reason = str(candidate.get("materializer_reason") or "Candidate extracted from master judgment payload.")
                if inference is not None:
                    edge_type = inference.edge_type
                    confidence = max(confidence, inference.confidence)
                    reason = inference.reason
                elif raw_outcome in {"fail", "failed", "fails", "not_satisfied"}:
                    edge_type = "FAILS_ELEMENT"
                    confidence = max(confidence, 0.6)
                elif raw_outcome in {"needs_review", "unknown", ""}:
                    confidence = min(confidence, 0.59)
                status = "active" if confidence >= 0.65 and raw_outcome not in {"needs_review", "unknown", ""} else "needs_review"
                upsert_edge_counted(
                    store=store,
                    counts=counts,
                    count_key="satisfiesElementEdges" if edge_type == "SATISFIES_ELEMENT" else "failsElementEdges",
                    edge_type=edge_type,
                    source_node_id=source_id,
                    source_node_type=source_type,
                    target_node_id=definition.element_id,
                    target_node_type="ClaimElement",
                    confidence=confidence,
                    status=status,
                    provenance={
                        **base_provenance,
                        "validation_status": status,
                        "source_properties": {"text": source_text or context_text[:900], "segment_index": source_index},
                        "target_properties": {
                            "element_id": definition.element_id,
                            "label": definition.label,
                            "sequence_no": definition.sequence_no,
                            "temporal_gate": definition.temporal_gate,
                        },
                    },
                    evidence={
                        "source_document_id": document_id,
                        "source_paragraph": candidate.get("source_paragraph"),
                        "candidate_outcome": raw_outcome or "inferred",
                        "confidence": confidence,
                        "reason": reason,
                        "review_status": status,
                        "source_excerpt": (source_text or context_text)[:900],
                    },
                )
                produced_element_outcome = True

        if not produced_element_outcome and test.elements:
            fallback_element, fallback_outcome, fallback_confidence = fallback_review_mapping_for_test(test=test, context_text=context_text)
            source_id, source_type, source_text, source_index, inference = source_for_inferred_element(
                document_id=document_id,
                element=fallback_element,
                facts=facts,
                holdings=holdings,
                ratios=ratios,
                burdens=burdens,
                context_text=context_text,
            )
            edge_type = "FAILS_ELEMENT" if fallback_outcome == "failed" else "SATISFIES_ELEMENT"
            reason = (
                inference.reason
                if inference is not None
                else "No element phrase was strong enough for active mapping; created review-safe element outcome candidate from holding disposition."
            )
            upsert_edge_counted(
                store=store,
                counts=counts,
                count_key="satisfiesElementEdges" if edge_type == "SATISFIES_ELEMENT" else "failsElementEdges",
                edge_type=edge_type,
                source_node_id=source_id,
                source_node_type=source_type,
                target_node_id=fallback_element.element_id,
                target_node_type="ClaimElement",
                confidence=fallback_confidence,
                status="needs_review",
                provenance={
                    **base_provenance,
                    "validation_status": "needs_review",
                    "source_properties": {"text": source_text or context_text[:900], "segment_index": source_index},
                    "target_properties": {
                        "element_id": fallback_element.element_id,
                        "label": fallback_element.label,
                        "sequence_no": fallback_element.sequence_no,
                        "temporal_gate": fallback_element.temporal_gate,
                    },
                },
                evidence={
                    "source_document_id": document_id,
                    "source_paragraph": "review_safe_fallback",
                    "candidate_outcome": fallback_outcome,
                    "confidence": fallback_confidence,
                    "reason": reason,
                    "review_status": "needs_review",
                    "source_excerpt": (source_text or context_text)[:900],
                },
            )

    for index, burden in enumerate(burdens):
        text = item_text(burden, "text")
        if not text:
            continue
        allocated_to = str(burden.get("allocated_to") or "").strip() or "unknown_requires_authority"
        burden_status = "needs_review" if mode == "warn" or allocated_to == "unknown_requires_authority" else "active"
        standard_id = str(burden.get("standard_of_proof") or "").strip()
        if standard_id and not standard_id.startswith("StandardOfProof:"):
            standard_id = f"StandardOfProof:{standard_id}"
        if not standard_id:
            standard_id = standard_of_proof_id_from_text(text) or ""
        burden_id = f"BurdenOfProof:{document_id}:{sha256_text(text)[:12]}"
        source_id = node_id("Issue", document_id, 0) if issues else tests[0].elements[0].element_id
        source_type = "Issue" if issues else "ClaimElement"
        upsert_edge_counted(
            store=store,
            counts=counts,
            count_key="burdenEdges",
            edge_type="HAS_BURDEN",
            source_node_id=source_id,
            source_node_type=source_type,
            target_node_id=burden_id,
            target_node_type="BurdenOfProof",
            confidence=float(burden.get("confidence") or 0.58),
            status=burden_status,
            provenance={
                **base_provenance,
                "validation_status": "needs_review" if mode == "warn" else "materialized",
                "source_properties": {"text": item_text(issues[0], "issue_text", "text") if issues else tests[0].elements[0].label},
                "target_properties": {
                    "burden_id": burden_id,
                    "allocated_to": allocated_to,
                    "standard_id": standard_id or None,
                    "source_reference": burden.get("source_paragraph"),
                    "confidence": burden.get("confidence") or 0.58,
                },
            },
            evidence={
                "text": text,
                "confidence": burden.get("confidence") or 0.58,
                "party_role": allocated_to,
                "source_paragraph": burden.get("source_paragraph"),
                "source_document_id": document_id,
            },
        )
        if standard_id:
            upsert_edge_counted(
                store=store,
                counts=counts,
                count_key="standardEdges",
                edge_type="HAS_STANDARD",
                source_node_id=burden_id,
                source_node_type="BurdenOfProof",
                target_node_id=standard_id,
                target_node_type="StandardOfProof",
                confidence=float(burden.get("confidence") or 0.58),
                status="active",
                provenance={
                    **base_provenance,
                    "source_properties": {
                        "burden_id": burden_id,
                        "allocated_to": allocated_to,
                        "standard_id": standard_id,
                    },
                    "target_properties": {
                        "standard_id": standard_id,
                        "label": standard_of_proof_label(standard_id),
                        "jurisdiction": jurisdiction,
                    },
                },
                evidence={
                    "confidence": burden.get("confidence") or 0.58,
                    "source_document_id": document_id,
                },
            )

    for index, outcome in enumerate(outcomes):
        outcome_type = str(outcome.get("outcome_type") or "").strip() or "unknown"
        primary_order = str(outcome.get("primary_order_text") or "").strip()
        if not outcome_type and not primary_order:
            continue
        source_index = 0 if holdings else index
        source_id = node_id("Holding", document_id, min(source_index, max(0, len(holdings) - 1)))
        target_id = f"LegalOutcome:{document_id}:{sha256_text(outcome_type + primary_order)[:12]}"
        upsert_edge_counted(
            store=store,
            counts=counts,
            count_key="outcomeEdges",
            edge_type="RESULTS_IN",
            source_node_id=source_id,
            source_node_type="Holding",
            target_node_id=target_id,
            target_node_type="LegalOutcome",
            confidence=float(outcome.get("confidence") or 0.52),
            status="active" if float(outcome.get("confidence") or 0.52) >= 0.6 else "needs_review",
            provenance={
                **base_provenance,
                "source_properties": {"text": item_text(holdings[0], "holding_text", "text") if holdings else primary_order},
                "target_properties": {
                    "outcome_id": target_id,
                    "label": outcome_type.replace("_", " ").title(),
                    "disposition": outcome_type,
                    "relief": primary_order,
                    "confidence": outcome.get("confidence") or 0.52,
                },
            },
            evidence={
                "outcome_type": outcome_type,
                "primary_order_text": primary_order,
                "source_paragraph": outcome.get("source_paragraph"),
                "confidence": outcome.get("confidence") or 0.52,
                "source_document_id": document_id,
            },
        )
