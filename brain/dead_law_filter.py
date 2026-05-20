# /** file dead_law_filter.py filters stale legal authorities without discarding corpus retrieval hits [notes: unverified pins are treated as verification warnings, not dead-law proof] */
from __future__ import annotations

import re
from typing import Any, Callable


AuthorityResolver = Callable[[str, str | None], dict[str, Any] | None]

SUPPRESSION_TERMS = ("repealed", "superseded", "revoked", "historical", "overruled", "not good law")
GENERIC_CHAPTER_PATTERN = re.compile(r"^chapter\s+\d+\b", re.IGNORECASE)
GENERIC_SOURCE_REFERENCES = {"parliament", "tanzlii", "judiciary", "court", "gazette"}


def filter_authorities_with_resolver(
    *,
    authorities: list[dict[str, Any]],
    jurisdiction: str | None,
    resolve_authority: AuthorityResolver,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    filtered: list[dict[str, Any]] = []
    suppressed: list[dict[str, Any]] = []
    rewrites: list[str] = []

    for item in authorities:
        reference = str(item.get("reference") or "").strip()
        title = str(item.get("title") or reference).strip()
        haystack = f"{reference}\n{title}".lower()
        graph_node = resolve_authority(reference, jurisdiction)
        item["graphNode"] = graph_node

        suppress_reason: str | None = None
        if any(term in haystack for term in SUPPRESSION_TERMS):
            suppress_reason = "keyword_dead_law"
        pin = item.get("pin")
        if reference.lower() in GENERIC_SOURCE_REFERENCES and not (isinstance(pin, dict) and bool(pin.get("verified"))):
            suppress_reason = suppress_reason or "generic_source_reference"
        if GENERIC_CHAPTER_PATTERN.match(reference) and not (isinstance(pin, dict) and bool(pin.get("verified"))):
            suppress_reason = suppress_reason or "generic_chapter_reference"
        topic_mismatch = float(item.get("topic_mismatch_score") or 0.0)
        quality_score = float(item.get("authority_quality_score") or 0.0)
        if topic_mismatch >= 0.45 and not (isinstance(pin, dict) and bool(pin.get("verified"))) and quality_score < 0.95:
            suppress_reason = suppress_reason or "topic_mismatch_unverified"

        if suppress_reason:
            suppressed_item = {**item, "suppressionReason": suppress_reason}
            suppressed.append(suppressed_item)
            replacement = rewrite_for_dead_law(suppressed_item)
            if replacement:
                rewrites.append(replacement)
            continue

        filtered.append(item)

    return filtered, suppressed, rewrites


def rewrite_for_dead_law(item: dict[str, Any]) -> str | None:
    suppression_reason = str(item.get("suppressionReason") or "").strip()
    if suppression_reason in {"generic_chapter_reference", "generic_source_reference", "topic_mismatch_unverified"}:
        return None
    reference = str(item.get("reference") or item.get("title") or "").strip()
    if not reference:
        return None
    graph_node = item.get("graphNode")
    if isinstance(graph_node, dict):
        replacement = str(graph_node.get("citation_text") or graph_node.get("act_name") or graph_node.get("title") or "").strip()
        if replacement and replacement.lower() != reference.lower():
            return f"{reference} is no longer good law. The current authority is {replacement}."
    return f"{reference} is no longer good law and must not be relied on without identifying the current authority."
