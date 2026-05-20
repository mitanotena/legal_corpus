from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
import re
from typing import Any


ADVERSE_HISTORY_RELATIONS = {
    "overrules",
    "overruled",
    "overruled_by",
    "ovrrules",
    "reverses",
    "reversed",
    "reversed_by",
    "reverses_on_appeal",
    "reversed_on_appeal",
    "sets_aside",
    "set_aside",
    "vacates",
    "vacated",
}


@dataclass(frozen=True, slots=True)
class ProceduralHistoryEntry:
    court: str
    judge: str
    date: str
    outcome: str
    order_made: str
    is_current_binding_version: bool
    source_reference: str = ""
    affected_reference: str = ""
    binding_authority: str = ""
    treatment_type: str = ""
    direction: str = ""
    quote: str = ""
    source_paragraph: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ProceduralHistoryAssessment:
    has_adverse_history: bool
    affected_reference: str
    binding_authority: str
    warning: str
    entries: tuple[ProceduralHistoryEntry, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["entries"] = [entry.to_dict() for entry in self.entries]
        return payload


def analyze_procedural_history(
    *,
    graph_evidence: list[dict[str, Any]] | None,
) -> ProceduralHistoryAssessment | None:
    entries: list[ProceduralHistoryEntry] = []
    for item in graph_evidence or []:
        fallback_reference = _text(item.get("reference") or item.get("citation") or item.get("title"))
        for raw_entry in list(item.get("procedural_history") or []):
            if not isinstance(raw_entry, dict):
                continue
            entry = procedural_history_entry_from_mapping(raw_entry, fallback_reference=fallback_reference)
            if entry is not None:
                entries.append(entry)

    adverse_entries = [
        entry
        for entry in entries
        if not entry.is_current_binding_version or _relation_key(entry.treatment_type) in ADVERSE_HISTORY_RELATIONS
    ]
    if not adverse_entries:
        return None

    adverse_entries.sort(key=lambda entry: (not bool(entry.binding_authority), -entry.confidence, entry.date), reverse=False)
    entry = adverse_entries[0]
    affected_reference = entry.affected_reference or entry.source_reference or "This decision"
    binding_authority = entry.binding_authority or entry.source_reference or "the later appellate authority"
    warning = _warning_for_entry(entry, affected_reference=affected_reference, binding_authority=binding_authority)
    return ProceduralHistoryAssessment(
        has_adverse_history=True,
        affected_reference=affected_reference,
        binding_authority=binding_authority,
        warning=warning,
        entries=tuple(adverse_entries),
    )


def render_procedural_history_graph_lines(assessment: ProceduralHistoryAssessment | None) -> list[str]:
    if assessment is None or not assessment.entries:
        return []
    lines = ["  [PROCEDURAL HISTORY WARNING]", f"  {assessment.warning}"]
    for entry in assessment.entries[:3]:
        if entry.affected_reference:
            lines.append(f"  Affected Authority: {entry.affected_reference}")
        if entry.binding_authority:
            lines.append(f"  Current Binding Version: false | Binding Authority: {entry.binding_authority}")
        else:
            lines.append("  Current Binding Version: false")
        if entry.outcome:
            lines.append(f"  Appellate Outcome: {entry.outcome}")
        if entry.order_made:
            lines.append(f"  Order Made: {entry.order_made}")
        if entry.court or entry.date:
            court_date = " | ".join(part for part in (entry.court, entry.date) if part)
            lines.append(f"  Procedural Source: {court_date}")
        if entry.quote:
            lines.append(f"  Source: {entry.quote}")
    return lines


def load_procedural_history_for_documents(
    pipeline: Any,
    document_ids: list[str],
    *,
    limit_per_document: int = 3,
) -> dict[str, list[dict[str, Any]]]:
    """Load appeal/reversal history for retrieved judgments from the legal corpus.

    The function accepts the shared crawler pipeline/store shape and intentionally
    reads existing corpus tables. It fails closed to an empty mapping if the
    local database is older than this feature.
    """
    normalized_ids = [str(item or "").strip() for item in document_ids if str(item or "").strip()]
    if not normalized_ids or not hasattr(pipeline, "store") or not hasattr(pipeline.store, "connect"):
        return {}

    output: dict[str, list[dict[str, Any]]] = {document_id: [] for document_id in normalized_ids}
    with pipeline.store.connect() as conn:
        _load_from_doctrinal_edges(conn, output, normalized_ids, limit_per_document=limit_per_document)
        _load_from_legal_edges(conn, output, normalized_ids, limit_per_document=limit_per_document)
        _load_from_citation_links(conn, output, normalized_ids, limit_per_document=limit_per_document)
    return {document_id: entries for document_id, entries in output.items() if entries}


def procedural_history_entry_from_mapping(
    value: dict[str, Any],
    *,
    fallback_reference: str = "",
) -> ProceduralHistoryEntry | None:
    treatment_type = _relation_key(
        value.get("treatment_type")
        or value.get("relation")
        or value.get("edge_type")
        or value.get("status")
    )
    is_current = value.get("is_current_binding_version")
    if is_current is None:
        is_current = not (treatment_type in ADVERSE_HISTORY_RELATIONS)
    affected_reference = _text(
        value.get("affected_reference")
        or value.get("target_reference")
        or value.get("subordinate_reference")
        or fallback_reference
    )
    source_reference = _text(
        value.get("source_reference")
        or value.get("appeal_reference")
        or value.get("current_reference")
        or value.get("reference")
    )
    binding_authority = _text(
        value.get("binding_authority")
        or value.get("binding_reference")
        or value.get("controlling_reference")
        or source_reference
    )
    if not affected_reference and not binding_authority:
        return None
    return ProceduralHistoryEntry(
        court=_text(value.get("court") or value.get("source_court") or value.get("appeal_court")),
        judge=_text(value.get("judge") or value.get("source_judge") or value.get("appeal_judge")),
        date=_text(value.get("date") or value.get("decision_date") or value.get("appeal_date")),
        outcome=_text(value.get("outcome") or value.get("appellate_outcome") or value.get("result")),
        order_made=_text(value.get("order_made") or value.get("order") or value.get("relief")),
        is_current_binding_version=bool(is_current),
        source_reference=source_reference,
        affected_reference=affected_reference,
        binding_authority=binding_authority,
        treatment_type=treatment_type,
        direction=_text(value.get("direction")),
        quote=_text(value.get("quote") or value.get("evidence_excerpt") or value.get("context_excerpt")),
        source_paragraph=_text(value.get("source_paragraph") or value.get("paragraph_anchor")),
        confidence=max(0.0, min(1.0, float(value.get("confidence") or 0.0))),
    )


def _load_from_doctrinal_edges(
    conn: Any,
    output: dict[str, list[dict[str, Any]]],
    document_ids: list[str],
    *,
    limit_per_document: int,
) -> None:
    if not _table_exists(conn, "document_doctrinal_edges"):
        return
    placeholders = ",".join("?" for _ in document_ids)
    rows = conn.execute(
        f"""
        SELECT
            dde.source_document_id,
            dde.target_document_id,
            dde.relation,
            dde.confidence,
            dde.metadata_json,
            sd.title AS source_title,
            sd.citation AS source_citation,
            sd.court AS source_court,
            sd.publication_date AS source_date,
            td.title AS target_title,
            td.citation AS target_citation,
            td.court AS target_court
        FROM document_doctrinal_edges dde
        LEFT JOIN documents sd ON sd.id = dde.source_document_id
        LEFT JOIN documents td ON td.id = dde.target_document_id
        WHERE lower(COALESCE(dde.relation, '')) IN ({",".join("?" for _ in ADVERSE_HISTORY_RELATIONS)})
          AND (dde.source_document_id IN ({placeholders}) OR dde.target_document_id IN ({placeholders}))
        ORDER BY dde.confidence DESC, dde.updated_at DESC
        """,
        (*sorted(ADVERSE_HISTORY_RELATIONS), *document_ids, *document_ids),
    ).fetchall()
    for row in rows:
        relation = _relation_key(row["relation"])
        source_document_id = _text(row["source_document_id"])
        target_document_id = _text(row["target_document_id"])
        source_reference = _reference(row["source_citation"], row["source_title"], source_document_id)
        target_reference = _reference(row["target_citation"], row["target_title"], target_document_id)
        metadata = _safe_json(row["metadata_json"])
        if target_document_id in output:
            _append_history(
                output,
                target_document_id,
                {
                    "direction": "incoming",
                    "treatment_type": relation,
                    "affected_reference": target_reference,
                    "source_reference": source_reference,
                    "binding_authority": source_reference,
                    "court": row["source_court"],
                    "date": row["source_date"],
                    "outcome": metadata.get("appellate_outcome") or metadata.get("outcome") or _default_outcome(relation),
                    "order_made": metadata.get("order_made") or metadata.get("order"),
                    "quote": metadata.get("context_excerpt") or metadata.get("quote"),
                    "source_paragraph": metadata.get("paragraph_anchor") or metadata.get("source_paragraph"),
                    "confidence": row["confidence"],
                    "is_current_binding_version": False,
                },
                limit_per_document=limit_per_document,
            )
        if source_document_id in output:
            _append_history(
                output,
                source_document_id,
                {
                    "direction": "outgoing",
                    "treatment_type": relation,
                    "affected_reference": target_reference,
                    "source_reference": source_reference,
                    "binding_authority": source_reference,
                    "court": row["source_court"],
                    "date": row["source_date"],
                    "outcome": metadata.get("appellate_outcome") or metadata.get("outcome") or _default_outcome(relation),
                    "order_made": metadata.get("order_made") or metadata.get("order"),
                    "quote": metadata.get("context_excerpt") or metadata.get("quote"),
                    "source_paragraph": metadata.get("paragraph_anchor") or metadata.get("source_paragraph"),
                    "confidence": row["confidence"],
                    "is_current_binding_version": True,
                },
                limit_per_document=limit_per_document,
            )


def _load_from_legal_edges(
    conn: Any,
    output: dict[str, list[dict[str, Any]]],
    document_ids: list[str],
    *,
    limit_per_document: int,
) -> None:
    if not _table_exists(conn, "legal_edges"):
        return
    placeholders = ",".join("?" for _ in document_ids)
    edge_types = (
        "OVERRULES",
        "OVERRULED_BY",
        "REVERSES",
        "REVERSED_BY",
        "REVERSES_ON_APPEAL",
        "REVERSED_ON_APPEAL",
        "SETS_ASIDE",
    )
    rows = conn.execute(
        f"""
        SELECT
            e.source_node_id,
            e.source_document_id,
            e.edge_type,
            e.target_node_id,
            e.confidence,
            e.evidence_json,
            sd.title AS source_title,
            sd.citation AS source_citation,
            sd.court AS source_court,
            sd.publication_date AS source_date,
            td.id AS target_document_id,
            td.title AS target_title,
            td.citation AS target_citation,
            td.court AS target_court
        FROM legal_edges e
        LEFT JOIN documents sd ON sd.id = COALESCE(e.source_document_id, CASE WHEN instr(e.source_node_id, ':') > 0 THEN substr(e.source_node_id, instr(e.source_node_id, ':') + 1) ELSE NULL END)
        LEFT JOIN documents td ON td.id = CASE WHEN instr(e.target_node_id, ':') > 0 THEN substr(e.target_node_id, instr(e.target_node_id, ':') + 1) ELSE NULL END
        WHERE e.edge_type IN ({",".join("?" for _ in edge_types)})
          AND e.status IN ('active', 'needs_review')
          AND (
            COALESCE(e.source_document_id, CASE WHEN instr(e.source_node_id, ':') > 0 THEN substr(e.source_node_id, instr(e.source_node_id, ':') + 1) ELSE NULL END) IN ({placeholders})
            OR CASE WHEN instr(e.target_node_id, ':') > 0 THEN substr(e.target_node_id, instr(e.target_node_id, ':') + 1) ELSE NULL END IN ({placeholders})
          )
        ORDER BY e.confidence DESC, e.updated_at DESC
        """,
        (*edge_types, *document_ids, *document_ids),
    ).fetchall()
    for row in rows:
        source_document_id = _text(row["source_document_id"]) or _node_tail(row["source_node_id"])
        target_document_id = _text(row["target_document_id"]) or _node_tail(row["target_node_id"])
        relation = _relation_key(row["edge_type"])
        evidence = _safe_json(row["evidence_json"])
        source_reference = _text(evidence.get("source_reference") or evidence.get("binding_authority")) or _reference(
            row["source_citation"], row["source_title"], source_document_id
        )
        target_reference = _text(evidence.get("affected_reference") or evidence.get("citation_text")) or _reference(
            row["target_citation"], row["target_title"], target_document_id
        )
        if target_document_id in output:
            _append_history(
                output,
                target_document_id,
                {
                    "direction": "incoming",
                    "treatment_type": relation,
                    "affected_reference": target_reference,
                    "source_reference": source_reference,
                    "binding_authority": evidence.get("binding_authority") or source_reference,
                    "court": evidence.get("court") or row["source_court"],
                    "date": evidence.get("date") or row["source_date"],
                    "outcome": evidence.get("outcome") or evidence.get("appellate_outcome") or _default_outcome(relation),
                    "order_made": evidence.get("order_made") or evidence.get("order") or evidence.get("overruling_reason"),
                    "quote": evidence.get("quote") or evidence.get("context_excerpt") or evidence.get("overruling_reason"),
                    "source_paragraph": evidence.get("source_paragraph"),
                    "confidence": row["confidence"],
                    "is_current_binding_version": False,
                },
                limit_per_document=limit_per_document,
            )


def _load_from_citation_links(
    conn: Any,
    output: dict[str, list[dict[str, Any]]],
    document_ids: list[str],
    *,
    limit_per_document: int,
) -> None:
    if not _table_exists(conn, "document_citation_links"):
        return
    placeholders = ",".join("?" for _ in document_ids)
    rows = conn.execute(
        f"""
        SELECT
            l.document_id AS source_document_id,
            l.linked_document_id AS target_document_id,
            l.treatment_type,
            l.citation_text,
            l.confidence,
            l.metadata_json,
            sd.title AS source_title,
            sd.citation AS source_citation,
            sd.court AS source_court,
            sd.publication_date AS source_date,
            td.title AS target_title,
            td.citation AS target_citation
        FROM document_citation_links l
        LEFT JOIN documents sd ON sd.id = l.document_id
        LEFT JOIN documents td ON td.id = l.linked_document_id
        WHERE lower(COALESCE(l.treatment_type, '')) IN ({",".join("?" for _ in ADVERSE_HISTORY_RELATIONS)})
          AND COALESCE(l.linked_document_id, '') IN ({placeholders})
        ORDER BY l.confidence DESC, l.created_at DESC
        """,
        (*sorted(ADVERSE_HISTORY_RELATIONS), *document_ids),
    ).fetchall()
    for row in rows:
        target_document_id = _text(row["target_document_id"])
        if target_document_id not in output:
            continue
        metadata = _safe_json(row["metadata_json"])
        source_reference = _reference(row["source_citation"], row["source_title"], _text(row["source_document_id"]))
        target_reference = _reference(row["target_citation"], row["citation_text"], target_document_id)
        _append_history(
            output,
            target_document_id,
            {
                "direction": "incoming",
                "treatment_type": row["treatment_type"],
                "affected_reference": target_reference,
                "source_reference": source_reference,
                "binding_authority": metadata.get("binding_authority") or source_reference,
                "court": metadata.get("court") or row["source_court"],
                "date": metadata.get("date") or row["source_date"],
                "outcome": metadata.get("appellate_outcome") or metadata.get("outcome") or _default_outcome(row["treatment_type"]),
                "order_made": metadata.get("order_made") or metadata.get("overruling_reason"),
                "quote": metadata.get("context_excerpt") or metadata.get("quote"),
                "source_paragraph": metadata.get("source_paragraph") or metadata.get("paragraph_anchor"),
                "confidence": row["confidence"],
                "is_current_binding_version": False,
            },
            limit_per_document=limit_per_document,
        )


def _append_history(
    output: dict[str, list[dict[str, Any]]],
    document_id: str,
    payload: dict[str, Any],
    *,
    limit_per_document: int,
) -> None:
    if document_id not in output or len(output[document_id]) >= limit_per_document:
        return
    entry = procedural_history_entry_from_mapping(payload, fallback_reference=_text(payload.get("affected_reference")))
    if entry is None:
        return
    key = (
        _relation_key(entry.treatment_type),
        entry.affected_reference.lower(),
        entry.binding_authority.lower(),
        entry.outcome.lower(),
    )
    existing = {
        (
            _relation_key(item.get("treatment_type")),
            _text(item.get("affected_reference")).lower(),
            _text(item.get("binding_authority")).lower(),
            _text(item.get("outcome")).lower(),
        )
        for item in output[document_id]
    }
    if key in existing:
        return
    output[document_id].append(entry.to_dict())


def _warning_for_entry(entry: ProceduralHistoryEntry, *, affected_reference: str, binding_authority: str) -> str:
    relation = _relation_key(entry.treatment_type)
    if "high court" in affected_reference.lower() or "tzhc" in affected_reference.lower():
        court_phrase = "This High Court decision"
    else:
        court_phrase = "This decision"
    action = "reversed on appeal" if "reverse" in relation else "overruled" if "overrule" in relation else "set aside"
    return (
        f"{court_phrase} was {action}. The binding authority is {binding_authority}. "
        "This case should be cited only for the trial court's reasoning, not as binding precedent."
    )


def _table_exists(conn: Any, table_name: str) -> bool:
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name = ? LIMIT 1",
            (table_name,),
        ).fetchone()
    except Exception:
        return False
    return row is not None


def _safe_json(raw: object) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    if not isinstance(raw, str) or not raw.strip():
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _relation_key(value: object) -> str:
    raw = re.sub(r"\s+", "_", str(value or "").strip().lower().replace("-", "_"))
    aliases = {
        "overrules": "overrules",
        "overruled_by": "overruled_by",
        "reverses_on_appeal": "reverses_on_appeal",
        "reversed_on_appeal": "reversed_on_appeal",
        "reverses": "reverses",
        "reversed": "reversed",
        "reversed_by": "reversed_by",
        "sets_aside": "sets_aside",
        "set_aside": "sets_aside",
    }
    return aliases.get(raw, raw)


def _reference(citation: object, title: object, fallback: object) -> str:
    return _text(citation) or _text(title) or _text(fallback)


def _text(value: object) -> str:
    return str(value or "").strip()


def _node_tail(value: object) -> str:
    raw = _text(value)
    if ":" not in raw:
        return raw
    return raw.split(":", 1)[1].strip()


def _default_outcome(relation: object) -> str:
    key = _relation_key(relation)
    if "reverse" in key:
        return "appeal allowed; earlier decision reversed"
    if "overrule" in key:
        return "earlier authority overruled"
    if "set_aside" in key:
        return "earlier decision set aside"
    return "later procedural treatment affects current binding status"
