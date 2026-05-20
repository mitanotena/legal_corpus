from __future__ import annotations

from typing import Any

from shared.legal_corpus.brain.models import VerificationSummary
from shared.legal_corpus.brain.safety import authority_weight, disclaimer_required, find_unverified_propositions


def verify_brain_output(
    *,
    answer_body: str,
    citations: list[Any],
    filtered_authorities: list[dict[str, Any]],
    suppressed_authorities: list[dict[str, Any]],
    dead_law_rewrites: list[str],
    unresolved_structured: list[str],
    graph_evidence: list[dict[str, Any]] | None = None,
) -> tuple[VerificationSummary, list[str]]:
    verified_authorities: list[str] = []
    for citation in citations:
        reference = str(getattr(citation, "reference", "") or "").strip()
        if reference:
            verified_authorities.append(reference)

    suppressed_refs = [
        str(item.get("reference") or item.get("title") or "").strip()
        for item in suppressed_authorities
        if str(item.get("reference") or item.get("title") or "").strip()
    ]

    weighted_scores = [authority_weight(item) for item in filtered_authorities]
    base_score = sum(weighted_scores) / len(weighted_scores) if weighted_scores else 0.45

    lead_authority = filtered_authorities[0] if filtered_authorities else {}
    lead_pin = lead_authority.get("pin") if isinstance(lead_authority.get("pin"), dict) else None
    lead_pinned = bool(lead_pin.get("verified")) if isinstance(lead_pin, dict) else False
    lead_reference = str(lead_authority.get("reference") or "").strip().lower()
    lead_title = str(lead_authority.get("title") or "").strip().lower()
    lead_is_generic_chapter = lead_reference.startswith("chapter ") or lead_title.startswith("chapter ")
    legal_test_count = sum(len(list(item.get("legal_tests") or [])) for item in graph_evidence or [])
    burden_count = sum(len(list(item.get("burdens") or [])) for item in graph_evidence or [])
    doctrinal_signal_count = sum(len(list(item.get("doctrinal_signals") or [])) for item in graph_evidence or [])
    negative_signal_count = sum(
        1
        for item in graph_evidence or []
        for signal in list(item.get("doctrinal_signals") or [])
        if str(signal.get("relation") or "").strip().lower() in {"questioned_by", "distinguishes", "overrules", "reverses"}
    )

    if not filtered_authorities:
        base_score -= 0.15
    if lead_pinned:
        base_score += 0.05
    if legal_test_count > 0:
        base_score += min(0.08, 0.03 + (legal_test_count * 0.02))
    if burden_count > 0:
        base_score += min(0.06, 0.02 + (burden_count * 0.01))
    if doctrinal_signal_count > 0:
        base_score += min(0.05, 0.01 + (doctrinal_signal_count * 0.01))
    if lead_is_generic_chapter and not lead_pinned:
        base_score = min(base_score, 0.5)
    if unresolved_structured:
        base_score -= min(0.2, len(unresolved_structured) * 0.05)
    if suppressed_authorities:
        suppression_penalty = min(0.2, len(suppressed_authorities) * 0.04)
        if negative_signal_count > 0 or dead_law_rewrites:
            suppression_penalty *= 0.5
        base_score -= suppression_penalty

    citation_completeness = 1.0 if verified_authorities else 0.7
    score = max(0.0, min(1.0, round((base_score * 0.75) + (citation_completeness * 0.25), 2)))

    unverified_props = find_unverified_propositions(
        answer_body=answer_body,
        filtered_authorities=filtered_authorities,
    )
    if unverified_props:
        score = max(0.0, round(score - min(0.25, len(unverified_props) * 0.06), 2))

    if lead_is_generic_chapter and not lead_pinned:
        score = min(score, 0.5)

    if score >= 0.85 and not unresolved_structured and not unverified_props:
        status = "verified"
    elif score >= 0.7:
        status = "mixed"
    else:
        status = "unverified"

    summary = VerificationSummary(
        confidenceScore=score,
        verificationStatus=status,
        verifiedAuthorities=verified_authorities,
        suppressedAuthorities=suppressed_refs,
        unverifiedPropositions=unverified_props,
        deadLawRewrites=list(dead_law_rewrites),
        disclaimerEscalated=disclaimer_required(confidence_score=score),
    )

    warnings: list[str] = []
    if unresolved_structured:
        warnings.append(
            "Structured authority references could not all be pinned to the current corpus and should be checked manually."
        )
    if suppressed_refs:
        warnings.append(
            "One or more stale or unsafe authorities were suppressed before final answer generation."
        )
    warnings.extend(dead_law_rewrites)
    warnings.extend(unverified_props)
    if summary.disclaimerEscalated:
        warnings.append("Confidence is below the filing-ready threshold. Verify manually before relying on this output.")

    return summary, warnings
