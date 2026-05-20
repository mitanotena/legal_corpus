from __future__ import annotations

import json
from typing import Any

from shared.legal_corpus.brain.statute_temporal import select_temporal_section_version
from shared.legal_corpus.brain.statute_verbatim import verify_section_text_integrity


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


def load_statute_context_for_documents(pipeline: Any, document_ids: list[str], *, limit_per_document: int = 3) -> dict[str, list[dict[str, Any]]]:
    """Load statutory text linked to retrieved judgments via APPLIES_SECTION.

    Section versions are selected by the judgment/document date where available.
    Current text is only a fallback and is marked with warnings when historical and
    current versions diverge.
    """
    normalized_ids = [str(item or "").strip() for item in document_ids if str(item or "").strip()]
    if not normalized_ids or not hasattr(pipeline, "store") or not hasattr(pipeline.store, "connect"):
        return {}
    with pipeline.store.connect() as conn:
        integrity_columns = _integrity_select_columns(conn)
        rows = conn.execute(
            f"""
            SELECT
                substr(e.source_node_id, instr(e.source_node_id, ':') + 1) AS document_id,
                e.target_node_id AS canonical_section_id,
                e.evidence_json AS edge_evidence_json,
                d.publication_date AS decision_date,
                d.year AS decision_year,
                s.section_ref,
                s.normalized_section_ref,
                a.id AS canonical_act_id,
                COALESCE(a.title, a.label, a.id) AS act_title,
                v.id AS section_version_id,
                v.text_en,
                v.valid_from,
                v.valid_to,
                v.is_current_version,
                v.metadata_json
                {integrity_columns},
                EXISTS (
                    SELECT 1
                    FROM legal_edges sup
                    WHERE sup.edge_type = 'SUPERSEDES'
                      AND sup.target_node_id = v.id
                      AND sup.status IN ('active', 'needs_review')
                ) AS superseded
            FROM legal_edges e
            LEFT JOIN documents d ON d.id = substr(e.source_node_id, instr(e.source_node_id, ':') + 1)
            INNER JOIN canonical_sections s ON s.id = e.target_node_id
            INNER JOIN canonical_acts a ON a.id = s.canonical_act_id
            LEFT JOIN canonical_section_versions v ON v.canonical_section_id = s.id
            WHERE e.edge_type = 'APPLIES_SECTION'
              AND e.status IN ('active', 'needs_review')
              AND e.source_node_id IN ({", ".join("'Case:' || ?" for _ in normalized_ids)})
            ORDER BY document_id ASC, e.confidence DESC, a.label ASC, s.section_ref ASC
            """,
            tuple(normalized_ids),
        ).fetchall()

    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in rows:
        document_id = str(row["document_id"] or "").strip()
        if not document_id:
            continue
        grouped.setdefault((document_id, str(row["canonical_section_id"] or "")), []).append(dict(row))

    by_document: dict[str, list[dict[str, Any]]] = {}
    for (document_id, _section_id), candidates in grouped.items():
        entries = by_document.setdefault(document_id, [])
        if len(entries) >= limit_per_document:
            continue
        first = candidates[0]
        operative_date = str(first.get("decision_date") or "").strip()
        if not operative_date and first.get("decision_year"):
            operative_date = f"{int(first['decision_year'])}-12-31"
        resolved = select_temporal_section_version(candidates, operative_date=operative_date)
        if resolved is None:
            continue
        metadata = dict(resolved.get("metadata") or _safe_json(resolved.get("metadata_json")))
        warning = str(resolved.get("warning") or "").strip() or None
        commencement_warning = str(resolved.get("commencement_warning") or "").strip()
        if commencement_warning:
            warning = f"{warning} {commencement_warning}".strip() if warning else commencement_warning
        integrity = verify_section_text_integrity({**resolved, "metadata": metadata})
        if integrity.warning:
            warning = f"{warning} {integrity.warning}".strip() if warning else integrity.warning
        entries.append(
            {
                "act_title": str(resolved.get("act_title") or "").strip(),
                "section_ref": str(resolved.get("section_ref") or "").strip(),
                "section_version_id": str(resolved.get("section_version_id") or "").strip(),
                "text_en": integrity.text_en.strip(),
                "valid_from": resolved.get("valid_from"),
                "valid_to": resolved.get("valid_to"),
                "operative_date": resolved.get("operative_date"),
                "resolution_basis": resolved.get("resolution_basis"),
                "commencement_instrument": resolved.get("commencement_instrument"),
                "transitional_note": resolved.get("transitional_note"),
                "commencement_scope": resolved.get("is_act_level_or_section_level"),
                "source_start_char": integrity.source_start_char,
                "source_end_char": integrity.source_end_char,
                "source_text_sha256": integrity.source_text_sha256,
                "cleaned_section_sha256": integrity.cleaned_section_sha256,
                "recomputed_text_sha256": integrity.recomputed_text_sha256,
                "source_integrity_status": integrity.status,
                "source_url": metadata.get("source_url"),
                "warning": warning,
                "confidence_penalty": 0.35 if not integrity.ok else (0.15 if warning else 0.0),
            }
        )
    return by_document


def _integrity_select_columns(conn: Any) -> str:
    try:
        columns = {
            str(row["name"] if hasattr(row, "keys") else row[1])
            for row in conn.execute("PRAGMA table_info(canonical_section_versions)").fetchall()
        }
    except Exception:
        columns = set()
    fragments = []
    for column in (
        "source_start_char",
        "source_end_char",
        "source_text_sha256",
        "cleaned_section_sha256",
        "source_integrity_status",
    ):
        if column in columns:
            fragments.append(f", v.{column} AS {column}")
        else:
            fragments.append(f", NULL AS {column}")
    return "\n                ".join(fragments)
