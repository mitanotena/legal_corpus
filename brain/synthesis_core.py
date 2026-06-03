# /** file synthesis_core.py shared legal answer synthesis contract for Wakili brain [notes: supports simple-language style, model token callbacks, and agentic tool calling loop] */

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, Protocol

from shared.legal_corpus.brain.answer_contract import (
    AnswerType,
    classify_answer_type,
    required_leading_prefix,
    validate_answer_contract,
)
from shared.legal_corpus.brain.authority_safety import (
    analyze_authority_safety,
    render_authority_safety_application,
    render_authority_safety_graph_lines,
)
from shared.legal_corpus.brain.burden_certainty import (
    BurdenCertaintyLevel,
    assess_burden_certainty,
    burden_application_summary,
    burden_rule_summary,
)
from shared.legal_corpus.brain.distinguishing import (
    analyze_distinguishing,
    render_distinguishing_application,
    render_distinguishing_graph_lines,
)
from shared.legal_corpus.brain.element_application import render_element_application_summary
from shared.legal_corpus.brain.limitation_analysis import (
    LimitationAnalysis,
    analyze_limitation,
    is_limitation_prompt,
    render_limitation_application,
    render_limitation_graph_lines,
    render_limitation_rule,
)
from shared.legal_corpus.brain.procedural_history import (
    analyze_procedural_history,
    render_procedural_history_graph_lines,
)
from shared.legal_corpus.brain.practical_litigation import (
    analyze_practical_outcomes,
    is_practical_outcome_prompt,
    render_practical_outcome_answer,
    render_practical_outcome_graph_lines,
)
from shared.legal_corpus.brain.source_safety import (
    analyze_source_safety,
    render_source_safety_application,
    render_source_safety_graph_lines,
)
from shared.legal_corpus.brain.stare_decisis import (
    analyze_stare_decisis,
    render_stare_decisis_graph_lines,
)

NATURAL_CHAT_TOKENS = 400
LEGAL_CHAT_TOKENS = 900
VOICE_CHAT_TOKENS = 220

CONVERSATIONAL_LEGAL_PREAMBLES = [
    "Here's my analysis of that question:",
    "Let me break this down for you:",
    "Looking at the relevant law and cases, here's what I found:",
    "This is an important legal question. Here's how the law addresses it:",
]


class ModelUsageLike(Protocol):
    def to_dict(self) -> dict[str, Any]:
        ...


class ModelRouterResponseLike(Protocol):
    """Matches the ModelResponse dataclass from model_router.py"""
    content: str | None
    tool_calls: list[dict[str, Any]] | None
    usage: Any  # Bypass strict typing to avoid cross-module import issues


class ModelRouterLike(Protocol):
    def complete(
        self,
        *,
        mode: str,
        channel: str,
        messages: list[dict[str, Any]],
        max_tokens: int,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | dict | None = None,
        token_callback: Callable[[str], None] | None = None,
        reasoning_callback: Callable[[str], None] | None = None,
    ) -> ModelRouterResponseLike:
        ...


def _coerce_router_response(response: object) -> tuple[str, Any, list[dict[str, Any]] | None]:
    if isinstance(response, tuple):
        content = str(response[0] or "") if len(response) >= 1 else ""
        usage = response[1] if len(response) >= 2 else None
        return content, usage, None
    content = str(getattr(response, "content", "") or "")
    usage = getattr(response, "usage", None)
    raw_tool_calls = getattr(response, "tool_calls", None)
    tool_calls = raw_tool_calls if isinstance(raw_tool_calls, list) else None
    return content, usage, tool_calls


def _normalized_text_key(value: str) -> str:
    return " ".join(str(value or "").split()).strip().lower()


def _dedupe_text_blocks(values: list[str], *, blocked: set[str] | None = None) -> list[str]:
    output: list[str] = []
    seen = set(blocked or set())
    for value in values:
        normalized = _normalized_text_key(value)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        output.append(str(value).strip())
    return output


def _bounded_instruction_text(value: object, *, max_length: int = 900) -> str:
    text = " ".join(str(value or "").split()).strip()
    if len(text) <= max_length:
        return text
    return f"{text[: max_length - 3].rstrip()}..."


def _instruction_list(value: object, *, limit: int = 8, max_length: int = 220) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    seen: set[str] = set()
    for raw_item in value:
        text = _bounded_instruction_text(raw_item, max_length=max_length)
        normalized = _normalized_text_key(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        items.append(text)
        if len(items) >= limit:
            break
    return items


def _instruction_field(value: object, *, fallback: str = "Not specified") -> str:
    text = _bounded_instruction_text(value, max_length=140)
    return text or fallback


def _formatted_instruction_list(items: list[str]) -> str:
    if not items:
        return "- None recorded"
    return "\n".join(f"- {item}" for item in items)


def _build_conversational_preamble(user_message: str, dialogue_state: str) -> str:
    """
    Generate a brief conversational lead-in before legal analysis.
    This makes the response feel like a conversation turn, not a report dump.
    """
    del dialogue_state
    seed = _normalized_text_key(user_message)
    if "case" in seed or "judgment" in seed or "v " in seed:
        return "Looking at the relevant law and cases, here's what I found:"
    if "why" in seed or "how" in seed:
        return "Let me break this down for you:"
    return CONVERSATIONAL_LEGAL_PREAMBLES[sum(ord(char) for char in seed) % len(CONVERSATIONAL_LEGAL_PREAMBLES)]


def _build_conversational_prompt_instructions() -> str:
    return (
        "For this turn, respond naturally as a Tanzanian legal conversation partner.\n"
        "- Do not force CREAC, IRAC, memo headings, or labels unless the user asks for formal analysis.\n"
        "- Open like a lawyer in conversation: acknowledge the question, then give the practical first step.\n"
        "- You may use phrases like \"Good question\" or \"Let me check the procedural posture\" when they fit.\n"
        "- Ask only for essential missing details, especially dates, court level, parties, and jurisdiction.\n"
        "- Never invent case law, statutes, or section numbers; say when verified authority has not been retrieved."
    )


def _build_natural_chat_fallback_answer(
    *,
    prompt: str,
    missing_facts: list[str],
) -> str:
    """Build a safe conversational answer when the chat LLM is unavailable."""
    normalized = _normalized_text_key(prompt)
    if any(term in normalized for term in ("draft", "write", "prepare", "agreement", "contract", "lease")):
        return (
            "I can help draft that. To make it usable, send me the parties, key dates, governing jurisdiction, "
            "the transaction or dispute background, and the outcome you want the document to achieve."
        )
    if any(term in normalized for term in ("appeal", "rufaa")):
        return (
            "You may be able to appeal, but the first things to confirm are the judgment date, the court that issued it, "
            "and whether the decision was final or interlocutory. Once I have those, I can help map the deadline, forum, "
            "and documents needed."
        )
    if any(term in normalized for term in ("bail", "dhamana")):
        return (
            "Bail usually turns on the offence charged, the court, the procedural stage, and any statutory restrictions. "
            "Tell me the charge, court level, and whether this is before trial, after conviction, or pending appeal."
        )
    if "adverse possession" in normalized:
        return (
            "Adverse possession is the idea that a person who has occupied land openly, continuously, and without the owner's effective interruption "
            "may eventually defeat the registered owner's claim after the legally required time has run. For Tanzania, I would verify the current limitation "
            "provisions, land-registration position, and recent case law before treating this as filing-ready. The key facts are when occupation began, "
            "whether it was hostile rather than by permission, whether the owner interrupted possession, and what land records show."
        )
    if "criminal" in normalized and any(term in normalized for term in ("procedure", "process", "steps", "case")):
        return (
            "A criminal case usually moves through complaint or arrest, investigation, charge, first appearance or plea, "
            "bail consideration, disclosure and mentions, hearing or trial, judgment, sentence if there is a conviction, "
            "and then appeal or revision if a party challenges the outcome. To make this specific, tell me the offence, "
            "court level, and whether the matter is at arrest, plea, trial, sentence, or appeal stage."
        )
    if missing_facts:
        return (
            "I can help, but I need a few facts before giving a useful legal view: "
            f"{'; '.join(missing_facts[:3])}."
        )
    return (
        "I can help with that. Give me the key facts, jurisdiction, dates, and what you want to achieve, "
        "and I will separate practical analysis from any authority that still needs verification."
    )


def _contains_internal_fallback_scaffold(value: object) -> bool:
    normalized = _normalized_text_key(value)
    internal_markers = (
        "give a natural working answer",
        "no specific wakili authority was retrieved for citation in this turn",
        "start with the practical steps or intake questions the lawyer needs",
        "if the user wants a filing-ready position",
    )
    return any(marker in normalized for marker in internal_markers)


def _build_matter_standing_instruction_prompt(
    *,
    base_prompt: str,
    standing_instructions: dict[str, object] | None,
    final_framework: str,
) -> str:
    if not isinstance(standing_instructions, dict) or not standing_instructions:
        return base_prompt

    key_issues = _instruction_list(standing_instructions.get("keyIssues"), limit=12, max_length=180)
    caution_notes = _instruction_list(standing_instructions.get("cautionNotes"), limit=12, max_length=180)
    research_questions = _instruction_list(standing_instructions.get("researchQuestions"), limit=10, max_length=220)
    authority_preferences = _instruction_list(
        standing_instructions.get("authorityPreferences"),
        limit=10,
        max_length=180,
    )
    notes = _bounded_instruction_text(standing_instructions.get("notes"), max_length=900)
    raw_framework = _instruction_field(standing_instructions.get("reasoningFramework"), fallback=final_framework)
    reasoning_framework = final_framework if raw_framework.casefold() == "auto" else raw_framework

    block_parts = [
        "=== MATTER STANDING INSTRUCTIONS (LAYER 1) ===",
        "You MUST obey these matter constraints for this answer. Treat them as steering instructions, not as optional background.",
        f"- Jurisdiction: {_instruction_field(standing_instructions.get('jurisdiction'))}",
        f"- Reasoning Framework: {reasoning_framework}",
        f"- Agent Mode: {_instruction_field(standing_instructions.get('agentMode'))}",
        f"- Response Depth: {_instruction_field(standing_instructions.get('responseDepth'))}",
        "",
        "KEY ISSUES TO PROVE/DISPROVE:",
        _formatted_instruction_list(key_issues),
        "",
        "ABSOLUTE CAUTIONS:",
        "Do not suggest strategies, filings, or conclusions that violate these cautions.",
        _formatted_instruction_list(caution_notes),
        "",
        "PENDING RESEARCH QUESTIONS:",
        _formatted_instruction_list(research_questions),
        "",
        "AUTHORITY PREFERENCES:",
        _formatted_instruction_list(authority_preferences),
    ]
    if notes:
        block_parts.extend(["", "MATTER NOTES:", notes])
    block_parts.append("==============================================")

    base = str(base_prompt or "").strip()
    standing_block = "\n".join(block_parts)
    return f"{base}\n\n{standing_block}" if base else standing_block


def _private_document_sources_present(prompt: str) -> bool:
    return "<private_document_sources>" in str(prompt or "")


def _external_ai_processing_enabled(standing_instructions: dict[str, object] | None) -> bool:
    if not isinstance(standing_instructions, dict):
        return False
    return bool(standing_instructions.get("externalAiProcessingEnabled"))


def _synthesis_model_mode(
    *,
    prompt: str,
    standing_instructions: dict[str, object] | None,
) -> str:
    if _private_document_sources_present(prompt) and _external_ai_processing_enabled(standing_instructions):
        return "high_risk"
    if _private_document_sources_present(prompt):
        return "quick"
    return "standard"


def _apply_private_document_routing_instruction(
    *,
    system_prompt: str,
    prompt: str,
    standing_instructions: dict[str, object] | None,
) -> str:
    if not _private_document_sources_present(prompt):
        return system_prompt
    if _external_ai_processing_enabled(standing_instructions):
        return (
            f"{system_prompt}\n\n"
            "PRIVATE DOCUMENT ROUTING: External AI processing is enabled for this matter. "
            "Use the higher-risk synthesis lane for uploaded-document interpretation, while treating private-document excerpts as evidence only."
        ).strip()
    return (
        f"{system_prompt}\n\n"
        "PRIVATE DOCUMENT ROUTING: External AI processing is disabled for this matter. "
        "Answer conservatively based strictly on the provided text; do not infer external legal implications."
    ).strip()


def _is_layer_one_memory_read(item: dict[str, object]) -> bool:
    source = str(item.get("source") or "").strip()
    category = str(item.get("category") or "").strip()
    if source.startswith("matter.researchBrief."):
        return True
    return category in {"issue", "authority_preference"}


def _apply_matter_cautions_to_answer(
    *,
    answer: str,
    standing_instructions: dict[str, object] | None,
) -> str:
    if not isinstance(standing_instructions, dict):
        return answer
    cautions = _instruction_list(standing_instructions.get("cautionNotes"), limit=5, max_length=180)
    unresolved_conflicts = _pending_conflict_warnings(standing_instructions)
    if not cautions and not unresolved_conflicts:
        return answer
    normalized_answer = _normalized_text_key(answer)
    missing_cautions = [
        caution
        for caution in cautions
        if _normalized_text_key(caution) not in normalized_answer
    ]
    missing_conflicts = [
        conflict
        for conflict in unresolved_conflicts
        if _normalized_text_key(conflict) not in normalized_answer
    ]
    violation_warnings = _matter_caution_violation_warnings(answer=answer, cautions=cautions)
    if not missing_cautions and not missing_conflicts and not violation_warnings:
        return answer

    blocks: list[str] = []
    if missing_cautions:
        blocks.append("Matter Cautions:\n" + "\n".join(f"- {caution}" for caution in missing_cautions))
    if missing_conflicts:
        blocks.append("Unresolved Matter Conflicts:\n" + "\n".join(f"- {conflict}" for conflict in missing_conflicts))
    if violation_warnings:
        blocks.append("Matter Constraint Warning:\n" + "\n".join(f"- {warning}" for warning in violation_warnings))
    caution_block = "\n\n".join(blocks)
    insertion_marker = "\n\nRecommended Next Steps:"
    marker_index = answer.find(insertion_marker)
    if marker_index >= 0:
        return f"{answer[:marker_index]}\n\n{caution_block}{answer[marker_index:]}"
    return f"{answer.rstrip()}\n\n{caution_block}"


def _pending_conflict_warnings(standing_instructions: dict[str, object] | None) -> list[str]:
    if not isinstance(standing_instructions, dict):
        return []
    raw_items = standing_instructions.get("structuredItems")
    if not isinstance(raw_items, list):
        return []
    warnings: list[str] = []
    seen: set[str] = set()
    for raw_item in raw_items:
        if not isinstance(raw_item, dict):
            continue
        if str(raw_item.get("field") or "").strip() != "conflict_warning":
            continue
        if str(raw_item.get("reviewStatus") or "").strip() != "pending":
            continue
        text = _bounded_instruction_text(raw_item.get("text"), max_length=240)
        normalized = _normalized_text_key(text)
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        warnings.append(text)
        if len(warnings) >= 5:
            break
    return warnings


def _matter_caution_violation_warnings(*, answer: str, cautions: list[str]) -> list[str]:
    normalized_answer = _normalized_text_key(answer)
    if not normalized_answer:
        return []
    unsafe_action_cues = (
        "file immediately",
        "filing immediately",
        "prepare the filing immediately",
        "sue immediately",
        "proceed immediately",
        "send demand immediately",
        "no need to verify",
        "need not verify",
    )
    if not any(cue in normalized_answer for cue in unsafe_action_cues):
        return []
    warnings: list[str] = []
    for caution in cautions:
        normalized_caution = _normalized_text_key(caution)
        if any(cue in normalized_caution for cue in ("do not", "before verifying", "before checking", "mandatory", "strict")):
            warnings.append(
                "The draft answer used urgent action language that may conflict with an approved matter caution; verify the caution before advising action."
            )
            break
    return warnings


def _is_element_visibility_prompt(prompt: str) -> bool:
    normalized = " ".join(str(prompt or "").lower().split())
    if not normalized:
        return False
    cues = (
        "adverse possession",
        "must prove",
        "elements",
        "12-year",
        "12 year",
        "twelve-year",
        "twelve year",
        "temporal gate",
        "satisfied or failed",
    )
    return any(cue in normalized for cue in cues)


def _is_legal_research_query(prompt: str) -> bool:
    """
    Distinguish broad legal research from specific calculation requests.

    RESEARCH: "tell me about X", "show me cases", "what is the law on",
              "explain", "how do courts apply", "overview", "guide to"

    CALCULATION: "is my claim time-barred", "can I file", "does this apply to my case",
                 specific fact patterns requiring analysis gates
    """
    normalized = " ".join(str(prompt or "").lower().split())
    if not normalized:
        return True

    research_markers = (
        "tell me about",
        "show me",
        "what are the",
        "how do",
        "how does",
        "explain",
        "what is the law",
        "cases about",
        "case law on",
        "principle of",
        "overview",
        "guide to",
        "information on",
        "learn about",
        "understand",
        "area of law",
        "legal position",
        "recent developments",
        "leading cases",
        "key principles",
        "generally",
        "typically",
        "what happens when",
    )
    calculation_markers = (
        "my case",
        "my claim",
        "my matter",
        "my situation",
        "this case",
        "this claim",
        "this matter",
        "this situation",
        "can i file",
        "can i sue",
        "do i have",
        "is my",
        "claim barred",
        "barred by limitation",
        "within limitation",
        "does this apply to me",
        "what should i do",
        "time barred",
        "time-barred",
        "expired",
        "deadline",
        "accrual date",
        "how long do i have",
    )

    has_research = any(marker in normalized for marker in research_markers)
    has_calculation = any(marker in normalized for marker in calculation_markers)

    if has_calculation and not has_research:
        return False
    if has_research:
        return True

    word_count = len(normalized.split())
    has_my = " my " in f" {normalized} "
    return word_count < 15 and not has_my


def _is_burden_visibility_prompt(prompt: str) -> bool:
    normalized = " ".join(str(prompt or "").lower().split())
    if not normalized:
        return False
    cues = (
        "circumstantial evidence",
        "criminal appeals",
        "burden of proof",
        "beyond reasonable doubt",
        "safeguards must be satisfied",
        "identification evidence",
    )
    return any(cue in normalized for cue in cues)


def _is_dead_law_prompt(prompt: str) -> bool:
    normalized = " ".join(str(prompt or "").lower().split())
    if not normalized:
        return False
    cues = (
        "overruled case",
        "questioned",
        "reversed",
        "current filing",
        "current authority",
        "safely rely",
        "dead law",
    )
    return any(cue in normalized for cue in cues)


def _limitation_conclusion(analysis: LimitationAnalysis) -> str:
    if analysis.status == "BARRED":
        return "On the verified dates supplied, the claim is barred by limitation unless a pleaded exception or tolling fact is proven."
    if analysis.status == "AT_RISK":
        return "The limitation period is close to expiry; treat the matter as urgent and verify filing date, accrual, and interruptions."
    if analysis.status == "SAFE":
        return "On the verified dates supplied, the claim is not presently time-barred, but do not ignore jurisdiction-specific exceptions or tolling."
    return "Cannot confirm limitation status until accrual date, governing limitation period, and operative statute version are all verified."


def _reviewed_conflict_alerts(graph_evidence: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in graph_evidence or []:
        reference = str(item.get("reference") or "").strip()
        for alert in list(item.get("conflict_alerts") or []):
            if not isinstance(alert, dict):
                continue
            counterpart = str(alert.get("counterpart_reference") or "").strip()
            resolution_code = str(alert.get("resolution_code") or "").strip().lower()
            key = _normalized_text_key(f"{reference}|{counterpart}|{resolution_code}")
            if not key or key in seen:
                continue
            seen.add(key)
            enriched = dict(alert)
            enriched["source_reference"] = reference
            alerts.append(enriched)
    return alerts


def _conflict_analysis_summary(graph_evidence: list[dict[str, Any]] | None) -> str | None:
    alerts = _reviewed_conflict_alerts(graph_evidence)
    if not alerts:
        return None
    alert = alerts[0]
    source_reference = str(alert.get("source_reference") or "").strip() or "the retrieved authority"
    counterpart = str(alert.get("counterpart_reference") or "").strip() or "a reviewed counterpart authority"
    issue_text = str(alert.get("issue_text") or "").strip() or "the same doctrinal issue"
    shared_concepts = [str(item).strip() for item in list(alert.get("shared_concepts") or []) if str(item).strip()]
    concept_text = f" within {', '.join(shared_concepts[:2])}" if shared_concepts else ""
    resolution_code = str(alert.get("resolution_code") or "").replace("_", " ").strip()
    resolution_suffix = f" The reviewed conflict status is {resolution_code}." if resolution_code else ""
    return (
        f"{source_reference} does not stand alone: {counterpart} reached a contradictory result on {issue_text}{concept_text}."
        f"{resolution_suffix} Do not present the law as fully settled without naming that conflict."
    )


def _preferred_legal_test_evidence(graph_evidence: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    best_item: dict[str, Any] | None = None
    best_test: dict[str, Any] | None = None
    best_score = -1.0
    for item in graph_evidence or []:
        tests = list(item.get("legal_tests") or [])
        for test in tests:
            elements = list(test.get("elements") or [])
            score = float(test.get("confidence") or 0.0)
            score += len(elements) * 1.25
            if str(test.get("temporal_gate") or "").strip():
                score += 2.0
            if "adverse possession" in str(test.get("label") or "").strip().lower():
                score += 2.5
            if score > best_score:
                best_score = score
                best_item = item
                best_test = test
    if best_item is None or best_test is None:
        return None
    return {"item": best_item, "test": best_test}


def _preferred_burden_evidence(graph_evidence: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    best_item: dict[str, Any] | None = None
    best_burden: dict[str, Any] | None = None
    best_score = -1.0
    for item in graph_evidence or []:
        for burden in list(item.get("burdens") or []):
            score = float(burden.get("confidence") or 0.0)
            if str(burden.get("standard_label") or "").strip():
                score += 0.5
            if "prosecution" in str(burden.get("allocated_to") or "").lower():
                score += 0.5
            if score > best_score:
                best_score = score
                best_item = item
                best_burden = burden
    if best_item is None or best_burden is None:
        return None
    return {"item": best_item, "burden": best_burden}


def _legal_test_rule_summary(preferred: dict[str, Any]) -> str:
    item = dict(preferred.get("item") or {})
    test = dict(preferred.get("test") or {})
    reference = str(item.get("reference") or "").strip()
    label = str(test.get("label") or "Legal test").strip()
    temporal_gate = str(test.get("temporal_gate") or "").strip()
    elements = [str(element.get("label") or "").strip() for element in list(test.get("elements") or []) if str(element.get("label") or "").strip()]
    parts = []
    if reference:
        parts.append(f"{reference} applies the {label.lower()}")
    else:
        parts.append(f"The strongest retrieved authority applies the {label.lower()}")
    if temporal_gate:
        parts.append(f"and states the temporal gate as {temporal_gate}")
    if elements:
        parts.append("with elements including " + ", ".join(elements[:4]))
    return " ".join(parts).strip() + "."


def _legal_test_application_summary(preferred: dict[str, Any]) -> str:
    return render_element_application_summary(preferred)


def _burden_rule_summary(preferred: dict[str, Any]) -> str:
    item = dict(preferred.get("item") or {})
    reference = str(item.get("reference") or "").strip()
    assessment = assess_burden_certainty(prompt="", preferred_burden=preferred)
    return burden_rule_summary(assessment, reference=reference)


def _burden_application_summary(preferred: dict[str, Any]) -> str:
    assessment = assess_burden_certainty(prompt="", preferred_burden=preferred)
    return burden_application_summary(assessment)


def render_answer(
    *,
    prompt: str,
    channel: str,
    reasoning_framework: str,
    issue_map: list[dict[str, Any]],
    supporting_arguments: list[str],
    opposing_arguments: list[str],
    rebuttals: list[str],
    missing_facts: list[str],
    dead_law_rewrites: list[str],
    recommended_next_actions: list[str],
    graph_evidence: list[dict[str, Any]] | None = None,
    memory_reads: list[dict[str, Any]] | None = None,
    matter_standing_instructions: dict[str, object] | None = None,
    suppressed_authorities: list[dict[str, Any]] | None = None,
    model_router_factory: type[ModelRouterLike] | None = None,
    synthesis_system_prompt: str = "",
    token_callback: Callable[[str], None] | None = None,
    reasoning_callback: Callable[[str], None] | None = None,
    synthesis_mode_override: str | None = None,
    natural_chat_response: bool = False,
    simple_language: bool = False,
    tools: list[dict[str, Any]] | None = None,
    tool_executor: Callable[[str, dict[str, Any]], str] | None = None,
) -> tuple[str, bool, dict[str, Any]]:
    supporting_arguments = _dedupe_text_blocks(list(supporting_arguments or []))
    opposing_arguments = _dedupe_text_blocks(
        list(opposing_arguments or []),
        blocked={_normalized_text_key(item) for item in supporting_arguments},
    )
    rebuttals = _dedupe_text_blocks(
        list(rebuttals or []),
        blocked={_normalized_text_key(item) for item in [*supporting_arguments, *opposing_arguments]},
    )
    missing_facts = _dedupe_text_blocks(list(missing_facts or []))
    dead_law_rewrites = _dedupe_text_blocks(list(dead_law_rewrites or []))
    recommended_next_actions = _dedupe_text_blocks(list(recommended_next_actions or []))

    final_framework = "IRAC" if str(reasoning_framework or "").strip().upper() == "IRAC" else "CREAC"
    answer_type = classify_answer_type(prompt, reasoning_framework=final_framework)
    issue = issue_map[0]["issue"] if issue_map else "the main legal issue"
    rule = issue_map[0]["ruleSummary"] if issue_map else "Apply the strongest verified Tanzanian authority."
    application = issue_map[0]["applicationSummary"] if issue_map else "Fit the authority to the proven facts conservatively."
    provisional = issue_map[0]["provisionalConclusion"] if issue_map else "Manual verification remains necessary."
    is_research_query = _is_legal_research_query(prompt)
    preferred_legal_test = _preferred_legal_test_evidence(graph_evidence)
    preferred_burden = _preferred_burden_evidence(graph_evidence)
    burden_assessment = assess_burden_certainty(prompt=prompt, preferred_burden=preferred_burden)
    conflict_analysis = _conflict_analysis_summary(graph_evidence)
    authority_safety = analyze_authority_safety(graph_evidence=graph_evidence)
    source_safety = analyze_source_safety(graph_evidence=graph_evidence)
    limitation_analysis = None if is_research_query else analyze_limitation(prompt=prompt, graph_evidence=graph_evidence)
    procedural_history = analyze_procedural_history(graph_evidence=graph_evidence)
    practical_outcomes = analyze_practical_outcomes(graph_evidence=graph_evidence)
    distinguishing = analyze_distinguishing(graph_evidence=graph_evidence)
    stare_decisis = analyze_stare_decisis(graph_evidence=graph_evidence, prompt=prompt)
    if not is_research_query and _is_element_visibility_prompt(prompt) and preferred_legal_test:
        rule = _legal_test_rule_summary(preferred_legal_test)
        application = _legal_test_application_summary(preferred_legal_test)
    elif not is_research_query and is_limitation_prompt(prompt) and limitation_analysis is not None:
        rule = render_limitation_rule(limitation_analysis)
        application = render_limitation_application(limitation_analysis)
        provisional = _limitation_conclusion(limitation_analysis)
        if limitation_analysis.status == "CANNOT_CONFIRM":
            missing_facts = _dedupe_text_blocks(
                [
                    *missing_facts,
                    "Verified accrual date, applicable limitation period, and operative statute version are required for limitation analysis.",
                ]
            )
    elif is_practical_outcome_prompt(prompt) and practical_outcomes is not None:
        practical_answer = render_practical_outcome_answer(practical_outcomes)
        if practical_answer:
            rule = "Practical litigation outcomes must be reported from extracted orders, relief, costs, damages, interest, sentence, or judgment metadata."
            application = practical_answer
            provisional = "Verify the order wording and any currency/interest computation against the judgment text before using it in advice or pleadings."
            recommended_next_actions = _dedupe_text_blocks(
                [
                    *recommended_next_actions,
                    "Retrieve the governing limitation provision operative at accrual and verify any tolling or interruption facts.",
                ]
            )
    elif _is_burden_visibility_prompt(prompt):
        rule = burden_rule_summary(
            burden_assessment,
            reference=str((preferred_burden or {}).get("item", {}).get("reference") or "").strip(),
        )
        application = burden_application_summary(burden_assessment)
        if burden_assessment.certainty == BurdenCertaintyLevel.UNKNOWN:
            provisional = "Do not state burden or standard conclusively until controlling authority is retrieved."
    elif _is_dead_law_prompt(prompt) and (dead_law_rewrites or suppressed_authorities):
        rule = (
            "A questioned, reversed, or overruled authority is not safe as a primary basis for a current Tanzanian filing."
        )
        application = (
            "Suppress the stale line, explain why it is unsafe, and replace it with the strongest current controlling authority before advising or filing."
        )
        provisional = "Treat historical or impaired authority as background only unless the current line expressly preserves it."
    if procedural_history is not None:
        application = f"{application.rstrip('.')} {procedural_history.warning}"
        provisional = (
            f"Do not cite {procedural_history.affected_reference} as binding precedent; "
            f"lead with {procedural_history.binding_authority} unless a lawyer verifies a narrower surviving point."
        )
    distinction_application = render_distinguishing_application(distinguishing)
    if distinction_application:
        application = f"{application.rstrip('.')} {distinction_application}"
        if distinguishing and distinguishing.entries and distinguishing.entries[0].needs_review:
            provisional = "Do not rely on the distinguished authority until the reason for distinction is reviewed against the judgment text."
    authority_safety_application = render_authority_safety_application(authority_safety)
    if authority_safety_application:
        application = f"{application.rstrip('.')} {authority_safety_application}"
        if authority_safety and authority_safety.obiter_only:
            rule = "Obiter is non-binding judicial commentary and cannot be used as the primary governing rule."
            provisional = "Find a binding ratio, holding, statute, or controlling appellate authority before presenting the proposition as law."
    source_safety_application = render_source_safety_application(source_safety)
    if source_safety_application:
        application = f"{application.rstrip('.')} {source_safety_application}"
    if stare_decisis is not None:
        application = (
            f"{application.rstrip('.')} {stare_decisis.hierarchy_statement} "
            f"Treat {stare_decisis.controlling_reference} as controlling over {stare_decisis.subordinate_reference} "
            f"on {stare_decisis.issue_text or 'the conflict issue'}."
        )
        if stare_decisis.cross_track_warnings:
            application = f"{application} {stare_decisis.cross_track_warnings[0]}"
        provisional = (
            f"Lead with {stare_decisis.controlling_reference}; cite {stare_decisis.subordinate_reference} only if distinguished, "
            "confined to facts, or needed as background."
        )
    elif conflict_analysis:
        application = f"{application.rstrip('.')} {conflict_analysis}"
        provisional = "The relevant line is contested. Explain the reviewed contradiction before presenting any rule as settled."
    graph_lines: list[str] = []
    for item in graph_evidence or []:
        reference = str(item.get("reference") or "").strip()
        if not reference:
            continue
        graph_lines.append(f"- {reference}")
        topic_labels = [str(label).strip() for label in list(item.get("topic_labels") or []) if str(label).strip()]
        if topic_labels:
            graph_lines.append(f"  Topics: {', '.join(topic_labels[:4])}")
        statute_references = [str(label).strip() for label in list(item.get("statute_references") or []) if str(label).strip()]
        if statute_references:
            graph_lines.append(f"  Statutes: {', '.join(statute_references[:3])}")
        statutory_texts = list(item.get("statutory_texts") or [])
        for statute in statutory_texts[:2]:
            act_title = str(statute.get("act_title") or "").strip()
            section_ref = str(statute.get("section_ref") or "").strip()
            text_en = str(statute.get("text_en") or "").strip()
            warning = str(statute.get("warning") or "").strip()
            if not text_en:
                if warning:
                    graph_lines.append(f"  [STATUTORY TEXT BLOCKED: Section {section_ref} of {act_title}]")
                    graph_lines.append(f"  [WARNING: {warning}]")
                continue
            graph_lines.append(f'  [STATUTORY TEXT: Section {section_ref} of {act_title}: "{text_en[:1200]}"]')
            if warning:
                graph_lines.append(f"  [WARNING: {warning}]")
        principle_statements = list(item.get("principle_statements") or [])
        for principle in principle_statements[:2]:
            principle_text = str(principle.get("principle_text") or "").strip()
            if not principle_text:
                continue
            statement_type = str(principle.get("statement_type") or "principle").strip().lower() or "principle"
            graph_lines.append(f"  {statement_type.title()}: {principle_text}")
        doctrinal_signals = list(item.get("doctrinal_signals") or [])
        for signal in doctrinal_signals[:2]:
            relation = str(signal.get("relation") or "").strip().lower()
            counterpart = str(signal.get("counterpart_reference") or "").strip()
            if not relation or not counterpart:
                continue
            graph_lines.append(f"  Doctrinal Signal: {relation.replace('_', ' ')} -> {counterpart}")
        conflict_alerts = list(item.get("conflict_alerts") or [])
        for alert in conflict_alerts[:2]:
            counterpart = str(alert.get("counterpart_reference") or "").strip()
            issue_text = str(alert.get("issue_text") or "").strip()
            resolution_code = str(alert.get("resolution_code") or "").replace("_", " ").strip()
            shared_concepts = [str(value).strip() for value in list(alert.get("shared_concepts") or []) if str(value).strip()]
            if counterpart:
                graph_lines.append("  [CONFLICTING AUTHORITY ALERT]")
                graph_lines.append(
                    f"  Conflict: {counterpart} reached a contradictory outcome on {issue_text or 'the same doctrinal issue'}."
                )
                if shared_concepts:
                    graph_lines.append(f"    Shared Concepts: {', '.join(shared_concepts[:3])}")
                if resolution_code:
                    graph_lines.append(f"    Reviewed Status: {resolution_code}")
                review_note = str(alert.get("review_note") or "").strip()
                if review_note:
                    graph_lines.append(f"    Review Note: {review_note}")
        burdens = list(item.get("burdens") or [])
        for burden in burdens[:2]:
            allocated_to = str(burden.get("allocated_to") or "").replace("_", " ").strip()
            standard_label = str(burden.get("standard_label") or "").strip()
            source_text = str(burden.get("source_text") or "").strip()
            item_assessment = assess_burden_certainty(prompt=prompt, preferred_burden={"item": item, "burden": burden})
            burden_line = f"  Burden: {allocated_to}" if allocated_to else "  Burden: review required"
            if standard_label:
                burden_line += f" | Standard: {standard_label}"
            burden_line += f" | Certainty: {item_assessment.certainty.value.replace('_', ' ').lower()}"
            graph_lines.append(burden_line)
            if source_text:
                graph_lines.append(f"    Source: {source_text}")
            if item_assessment.caveat:
                graph_lines.append(f"    Caveat: {item_assessment.caveat}")
        legal_tests = list(item.get("legal_tests") or [])
        for test in legal_tests[:2]:
            test_label = str(test.get("label") or "").strip()
            if not test_label:
                continue
            temporal_gate = str(test.get("temporal_gate") or "").strip()
            if temporal_gate:
                graph_lines.append(f"  Legal Test: {test_label} (temporal gate: {temporal_gate})")
            else:
                graph_lines.append(f"  Legal Test: {test_label}")
            for element in list(test.get("elements") or [])[:4]:
                element_label = str(element.get("label") or "").strip()
                if not element_label:
                    continue
                result = dict(element.get("result") or {})
                status = str(result.get("status") or "").strip().lower()
                source_text = str(result.get("source_text") or "").strip()
                element_gate = str(element.get("temporal_gate") or "").strip()
                gate_suffix = f" [gate: {element_gate}]" if element_gate else ""
                if status:
                    source_suffix = f" via {source_text}" if source_text else ""
                    if status == "failed":
                        graph_lines.append(f"    Element Failed: {element_label}{gate_suffix}{source_suffix}. Legal consequence: the test is materially weakened unless this element is cured.")
                    elif status == "satisfied":
                        graph_lines.append(f"    Element Satisfied: {element_label}{gate_suffix}{source_suffix}. Legal consequence: provisionally supports that element, subject to verification.")
                    else:
                        graph_lines.append(f"    Element {status.title()}: {element_label}{gate_suffix}{source_suffix}")
                else:
                    graph_lines.append(f"    Element Insufficient Evidence: {element_label}{gate_suffix}. Legal consequence: do not treat this element as established.")
    if limitation_analysis is not None:
        graph_lines.extend(render_limitation_graph_lines(limitation_analysis))
    if practical_outcomes is not None:
        graph_lines.extend(render_practical_outcome_graph_lines(practical_outcomes))
    if procedural_history is not None:
        graph_lines.extend(render_procedural_history_graph_lines(procedural_history))
    if distinguishing is not None:
        graph_lines.extend(render_distinguishing_graph_lines(distinguishing))
    if authority_safety is not None:
        graph_lines.extend(render_authority_safety_graph_lines(authority_safety))
    if source_safety is not None:
        graph_lines.extend(render_source_safety_graph_lines(source_safety))
    if stare_decisis is not None:
        graph_lines.extend(render_stare_decisis_graph_lines(stare_decisis))
    graph_lines = _dedupe_text_blocks(graph_lines)
    suppressed_lines: list[str] = []
    for item in suppressed_authorities or []:
        reference = str(item.get("reference") or item.get("title") or "").strip()
        reason = str(item.get("suppressionReason") or "").replace("_", " ").strip()
        if not reference:
            continue
        line = f"- Suppressed: {reference}"
        if reason:
            line += f" ({reason})"
        suppressed_lines.append(line)
    suppressed_lines = _dedupe_text_blocks(suppressed_lines)[:5]

    if answer_type == AnswerType.DEFINITIONAL:
        sections = [
            f"Definition: {rule}",
            f"Source: {supporting_arguments[0] if supporting_arguments else 'Use the retrieved Tanzanian legal authority and verify the cited source before relying on the definition.'}",
            f"Practical Note: {application}",
        ]
    elif answer_type == AnswerType.PROCEDURAL_CHECKLIST:
        checklist_items = recommended_next_actions[:4] or [
            "Verify the governing statute, rule, and court practice direction.",
            "Confirm limitation, jurisdiction, filing forum, and required supporting documents.",
            "Check whether any exception, leave requirement, or urgent certificate applies.",
        ]
        sections = [
            "Checklist:\n" + "\n".join(f"- {item}" for item in checklist_items),
            f"Authority: {rule}",
            "Limits: Treat this as a corpus-grounded checklist, not a complete filing opinion, until court registry requirements and current rules are verified.",
        ]
    elif answer_type == AnswerType.COMPARATIVE_TABLE:
        sections = [
            f"Comparison: {issue}",
            f"Authority: {rule}",
            f"Practical Consequence: {application}",
        ]
    elif answer_type == AnswerType.REFUSAL:
        sections = [
            "Cannot Safely Answer: The retrieved corpus evidence is insufficient for a safe legal answer.",
            f"Reason: {provisional}",
            f"Next Step: {(recommended_next_actions or ['Retrieve controlling primary authority and verify the missing legal facts.'])[0]}",
        ]
    elif final_framework == "IRAC":
        sections = [
            f"Issue: {issue}",
            f"Rule: {rule}",
            f"Application: {application}",
            f"Conclusion: {provisional}",
        ]
    else:
        sections = [
            f"Conclusion: {provisional}",
            f"Rule: {rule}",
            f"Explanation: {supporting_arguments[0] if supporting_arguments else 'Rely on the strongest verified authority and avoid extending the proposition beyond the record.'}",
            f"Application: {application}",
            f"Conclusion: {provisional}",
        ]

    if channel == "voice":
        concise = [
            sections[0],
            f"Key Rule: {rule}",
            f"Main Risk: {opposing_arguments[0] if opposing_arguments else 'The opposing side may exploit factual gaps.'}",
            f"Next Action: {(recommended_next_actions or ['Verify the missing facts and controlling authorities before acting.'])[0]}",
        ]
        answer = "\n".join(concise)
        spoken_summary = True
    else:
        explanation_text = supporting_arguments[0] if supporting_arguments else "Rely on the strongest verified authority and avoid extending the proposition beyond the record."
        supporting_bullets = [
            item for item in supporting_arguments
            if _normalized_text_key(item) != _normalized_text_key(explanation_text)
        ][:3]
        detail_parts = [
            "\n".join(sections),
            "Why that position is supported:\n" + "\n".join(f"- {item}" for item in supporting_bullets),
            "What the other side may argue:\n" + "\n".join(f"- {item}" for item in opposing_arguments[:3]),
            "How I would treat that risk:\n" + "\n".join(f"- {item}" for item in rebuttals[:3]),
        ]
        if graph_lines:
            detail_parts.append("Authority signals:\n" + "\n".join(graph_lines[:24]))
        if missing_facts:
            detail_parts.append("Missing Facts:\n" + "\n".join(f"- {item}" for item in missing_facts[:5]))
        if dead_law_rewrites:
            detail_parts.append("Dead-Law Corrections:\n" + "\n".join(f"- {item}" for item in dead_law_rewrites[:5]))
        if suppressed_lines:
            detail_parts.append("Suppressed Authorities:\n" + "\n".join(suppressed_lines))
        if recommended_next_actions:
            detail_parts.append("Recommended Next Steps:\n" + "\n".join(f"- {item}" for item in recommended_next_actions[:5]))
        legal_analysis = "\n\n".join(detail_parts)
        preamble = _build_conversational_preamble(prompt, "DEEP_RESEARCH")
        answer = f"{preamble}\n\n{legal_analysis}"
        spoken_summary = False

    memory_context = [
        str(item.get("content") or "").strip()
        for item in memory_reads or []
        if isinstance(item, dict)
        and not _is_layer_one_memory_read(item)
        and str(item.get("content") or "").strip()
    ]
    blocked_prompt_blocks = {
        _normalized_text_key(item)
        for item in [
            issue,
            rule,
            application,
            provisional,
            *supporting_arguments,
            *opposing_arguments,
            *rebuttals,
            *missing_facts,
            *dead_law_rewrites,
            *recommended_next_actions,
        ]
    }
    memory_context = _dedupe_text_blocks(memory_context, blocked=blocked_prompt_blocks)[:3]

    usage_dict: dict[str, Any] = {
        "requestedMode": "standard",
        "selectedModel": "deterministic-synthesis",
        "fallbackModel": None,
        "latencyMs": 0,
        "timedOut": False,
        "partialResult": False,
    }
    llm_text = ""
    
    if model_router_factory is not None:
        router = model_router_factory()
        system_prompt = _build_matter_standing_instruction_prompt(
            base_prompt=synthesis_system_prompt,
            standing_instructions=matter_standing_instructions,
            final_framework=final_framework,
        )
        system_prompt = _apply_private_document_routing_instruction(
            system_prompt=system_prompt,
            prompt=prompt,
            standing_instructions=matter_standing_instructions,
        )
        synthesis_mode = str(synthesis_mode_override or "").strip().lower() or _synthesis_model_mode(
            prompt=prompt,
            standing_instructions=matter_standing_instructions,
        )
        if natural_chat_response:
            system_prompt = (
                f"{system_prompt}\n\n"
                f"{_build_conversational_prompt_instructions()}"
            ).strip()
        if simple_language:
            system_prompt = (
                f"{system_prompt}\n\n"
                "SIMPLE LANGUAGE MODE:\n"
                "- Use plain words and short sentences.\n"
                "- Define legal terms briefly the first time they appear.\n"
                "- Keep legal accuracy, authority caution, and citation safety unchanged.\n"
                "- Do not talk down to the lawyer; simplify the explanation, not the legal reasoning."
            ).strip()
        
        # Base messages payload
        messages = [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": "".join(
                    [
                        f"CLIENT QUERY:\n{prompt}\n\n",
                        (
                            "REQUESTED ANSWER SHAPE:\n"
                            "- Natural conversational answer\n"
                            "- Ask only for essential missing details\n\n"
                            if natural_chat_response
                            else f"REQUESTED ANSWER SHAPE:\n- Framework: {final_framework}\n- Channel: {channel}\n\n"
                        ),
                        (
                            "STYLE PREFERENCE:\n- Simple language: explain legal terms briefly and use shorter sentences.\n\n"
                            if simple_language
                            else ""
                        ),
                        (
                            "RECENT MATTER MEMORY (LAYER 3):\n"
                            + "\n".join(f"- {item}" for item in memory_context)
                            + "\n\n"
                            if memory_context
                            else ""
                        ),
                        (
                            "RETRIEVED LEGAL EVIDENCE (LAYER 2):\n"
                            + "\n".join(
                                line
                                for line in (
                                    "\n".join(graph_lines[:24]).splitlines()
                                    if graph_evidence
                                    else []
                                )
                            )
                            + "\n\n"
                            if graph_evidence and graph_lines
                            else ""
                        ),
                        (
                            "GENERATE THE FINAL RESPONSE DIRECTLY:\n"
                            "- Open with the conversational lead-in already present in the material.\n"
                            "- Preserve citations, statutes, jurisdiction, and balanced analysis.\n"
                            "- Do not compress this into a brief text message.\n"
                            "- Do not use headings named Supporting Position, Opposing Position, Rebuttal Strategy, or Graph Evidence.\n\n"
                            f"CURRENT DRAFT:\n{answer}"
                        ),
                    ]
                ),
            },
        ]

        # AGENTIC LOOP: Support for tool calling (max 3 loops to prevent runaway)
        max_loops = 3
        for loop_index in range(max_loops):
            is_final_loop = (loop_index == max_loops - 1)
            
            # If on final loop, force strict text generation to prevent hanging tool calls
            active_tools = None if is_final_loop else tools
            active_tool_choice = "none" if is_final_loop else ("auto" if tools else None)

            router_kwargs: dict[str, Any] = {
                "mode": synthesis_mode,
                "channel": channel,
                "messages": messages,
                "max_tokens": (
                    NATURAL_CHAT_TOKENS
                    if natural_chat_response and channel == "chat"
                    else LEGAL_CHAT_TOKENS
                    if channel == "chat"
                    else VOICE_CHAT_TOKENS
                ),
            }
            if active_tools is not None:
                router_kwargs["tools"] = active_tools
            if tools and active_tool_choice is not None:
                router_kwargs["tool_choice"] = active_tool_choice
            if token_callback is not None:
                router_kwargs["token_callback"] = token_callback
            if reasoning_callback is not None:
                router_kwargs["reasoning_callback"] = reasoning_callback

            response_content, response_usage, response_tool_calls = _coerce_router_response(router.complete(**router_kwargs))

            if response_usage:
                usage_dict = response_usage.to_dict()

            # If LLM triggered a tool call and we have an executor, handle it
            if response_tool_calls and tool_executor:
                # 1. Append the assistant's tool call request to the message history
                messages.append({
                    "role": "assistant",
                    "tool_calls": response_tool_calls
                })
                
                # 2. Execute each tool and append the results
                for tool_call in response_tool_calls:
                    func_name = tool_call["function"]["name"]
                    try:
                        func_args = json.loads(tool_call["function"]["arguments"])
                    except json.JSONDecodeError:
                        func_args = {}
                    
                    try:
                        result_str = tool_executor(func_name, func_args)
                    except Exception as e:
                        result_str = f"Error executing tool {func_name}: {str(e)}"
                        
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tool_call["id"],
                        "name": func_name,
                        "content": result_str
                    })
                
                # Loop back to router.complete with the new tool results in messages
                continue
            
            else:
                # No tool calls, extract the final text and break the loop
                llm_text = response_content
                break

    if llm_text:
        candidate = llm_text.strip()
        if natural_chat_response and channel == "chat":
            answer = candidate
        else:
            contract = validate_answer_contract(candidate, answer_type)
            required_prefix = required_leading_prefix(answer_type)
            if channel == "voice":
                has_voice_structure = "Key Rule:" in candidate and (
                    "Next Action:" in candidate or "Source Warning:" in candidate or "Main Risk:" in candidate
                )
                if has_voice_structure:
                    answer = candidate
            elif candidate.startswith(required_prefix) and contract.ok:
                answer = candidate
    elif natural_chat_response and channel == "chat":
        answer = _build_natural_chat_fallback_answer(prompt=prompt, missing_facts=missing_facts)

    if channel == "chat" and _contains_internal_fallback_scaffold(answer):
        answer = _build_natural_chat_fallback_answer(prompt=prompt, missing_facts=missing_facts)

    answer = _apply_matter_cautions_to_answer(
        answer=answer,
        standing_instructions=matter_standing_instructions,
    )

    return answer, spoken_summary, usage_dict
