from __future__ import annotations

from datetime import datetime, timezone
import re


AUTHORITY_PORTAL_CHROME_TERMS: tuple[str, ...] = (
    "search settings",
    "staff mail",
    "oag-mis",
    "faq",
    "contact us",
    "publications",
    "kiswahili",
    "english",
)

AUTHORITY_LEGAL_STRUCTURE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\barrangement of sections\b", re.IGNORECASE),
    re.compile(r"\bsection\s+\d+[A-Za-z]?\b", re.IGNORECASE),
    re.compile(r"\bpart\s+[ivxlcdm0-9]+\b", re.IGNORECASE),
    re.compile(r"\bcap\.?\s*\d+[A-Za-z]?\b", re.IGNORECASE),
    re.compile(r"\bact\s+no\.?\s*\d+\s+of\s+(?:19|20)\d{2}\b", re.IGNORECASE),
    re.compile(r"\brevised\s+edition(?:\s+of)?\s+(?:19|20)\d{2}\b", re.IGNORECASE),
    re.compile(r"\bprincipal\s+legislation\b", re.IGNORECASE),
)

REPAIR_FATAL_ERROR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"pdf extraction exceeded", re.IGNORECASE),
    re.compile(r"eof marker not found", re.IGNORECASE),
    re.compile(r"incorrect startxref pointer", re.IGNORECASE),
    re.compile(r"object\s+\d+\s+\d+\s+not defined", re.IGNORECASE),
    re.compile(r"cannot open broken document", re.IGNORECASE),
    re.compile(r"file data error", re.IGNORECASE),
    re.compile(r"no /root object", re.IGNORECASE),
)

PIPELINE_INVALIDATING_EVENTS: set[str] = {
    "alert_created",
    "alert_reconciliation_completed",
    "artifact_storage_reconciled",
    "crawler_maintenance_completed",
    "document_retry_completed",
    "failed_chunk_retry_completed",
    "manual_document_processing_completed",
    "missing_ingestion_document_reconciled",
    "missing_ingestion_reconcile_completed",
    "source_run_completed",
    "source_run_failed",
    "source_run_started",
}


def document_embed_eligible(document: dict[str, object]) -> bool:
    return bool(
        int(document.get("chunk_count") or 0) > 0
        and bool(document.get("full_text_extracted"))
        and bool(document.get("all_pages_processed"))
        and bool(document.get("structure_complete"))
        and not bool(document.get("review_required"))
    )


def requires_graph_identity(*, document_type: str, instrument_type: str) -> bool:
    normalized_document_type = str(document_type or "").strip().lower()
    normalized_instrument_type = str(instrument_type or "").strip().lower()
    return normalized_document_type in {"judgment", "act", "amendment"} or normalized_instrument_type in {
        "judgment",
        "act",
        "amendment",
    }


def annotate_chunks_with_graph_identity(
    chunks: list[dict[str, object]],
    graph_identity: dict[str, object],
) -> None:
    if not chunks:
        return
    graph_payload = {
        key: value
        for key, value in dict(graph_identity or {}).items()
        if value is not None and str(value).strip() != ""
    }
    graph_payload.setdefault("graph_identity_resolved", bool(graph_payload))
    for chunk in chunks:
        metadata = chunk.get("metadata") if isinstance(chunk.get("metadata"), dict) else {}
        merged_metadata = dict(metadata)
        merged_metadata.update(graph_payload)
        merged_metadata["metadata_injected"] = True
        merged_metadata["graph_metadata_injected"] = True
        chunk["metadata"] = merged_metadata


def paragraph_repair_recommended(document: dict[str, object]) -> bool:
    paragraph_count = int(document.get("paragraph_count") or 0)
    estimated_paragraph_count = int(document.get("estimated_paragraph_count") or paragraph_count or 0)
    missing_page_count = int(document.get("missing_page_count") or 0)

    if bool(document.get("partial_extraction")) or bool(document.get("review_required")):
        return True
    if not bool(document.get("all_pages_processed", True)):
        return True
    if missing_page_count > 0:
        return True
    if paragraph_count <= 0:
        return True
    if estimated_paragraph_count > 0 and paragraph_count < estimated_paragraph_count:
        return True
    return False


def deferred_extraction_repair_candidate(document: dict[str, object]) -> bool:
    extraction_method = str(
        document.get("pdf_extraction_method")
        or document.get("extraction_method")
        or ""
    ).strip().lower()
    stale_deferred_flag = extraction_method == "deferred" or bool(document.get("missing_ingestion"))
    suspicious_thin_shape = (
        int(document.get("page_count") or 0) <= 1
        or int(document.get("extracted_page_count") or 0) <= 1
        or int(document.get("paragraph_count") or 0) <= 3
        or int(document.get("heading_count") or 0) <= 1
    )
    return stale_deferred_flag and suspicious_thin_shape and str(document.get("source_name") or "") == "parliament"


def repair_candidate_key(document: dict[str, object]) -> str:
    return str(document.get("document_id") or "").strip() or str(document.get("source_url") or "").strip()


def is_fatal_repair_error(error_message: str | None) -> bool:
    normalized = str(error_message or "").strip()
    if not normalized:
        return False
    return any(pattern.search(normalized) for pattern in REPAIR_FATAL_ERROR_PATTERNS)


def parse_iso_utc(value: str | None) -> datetime | None:
    if not value:
        return None
    normalized = str(value).strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def authority_portal_chrome_signal_count(text: str) -> int:
    lowered = str(text or "").lower()
    if not lowered:
        return 0
    return sum(1 for term in AUTHORITY_PORTAL_CHROME_TERMS if term in lowered)


def authority_legal_signal_count(text: str) -> int:
    haystack = str(text or "")
    if not haystack:
        return 0
    return sum(1 for pattern in AUTHORITY_LEGAL_STRUCTURE_PATTERNS if pattern.search(haystack))


def slugify_label(value: str, *, fallback: str = "document") -> str:
    normalized = re.sub(r"[^a-z0-9\-]+", "-", str(value or "").strip().lower()).strip("-")
    return normalized if normalized else fallback


def safe_filename_stem(value: str, *, fallback: str = "document", max_length: int = 160) -> str:
    normalized = re.sub(r"\s+", "_", str(value or "").strip())
    normalized = re.sub(r"[^A-Za-z0-9._()&-]+", "_", normalized)
    normalized = re.sub(r"_+", "_", normalized).strip("._- ")
    if not normalized:
        normalized = fallback
    if len(normalized) > max_length:
        normalized = normalized[:max_length].rstrip("._- ")
    return normalized or fallback


def looks_like_website_shell_text(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text or "")).strip().lower()
    if not normalized:
        return False
    shell_markers = (
        "download pdf",
        "copy citation",
        "report a problem",
        "ask ai",
        "skip to document content",
        "loading pdf",
        "related documents",
        "document detail",
        "media neutral citation",
        "to the top",
    )
    marker_hits = sum(1 for marker in shell_markers if marker in normalized)
    return marker_hits >= 2


def looks_like_placeholder_body_text(
    *,
    title: str,
    body_text: str,
    metadata: dict[str, object],
) -> bool:
    normalized_title = re.sub(r"\s+", " ", str(title or "")).strip().lower()
    normalized_body = re.sub(r"\s+", " ", str(body_text or "")).strip()
    normalized_body_lower = normalized_body.lower()
    extraction_method = str(metadata.get("pdf_extraction_method") or metadata.get("extraction_method") or "").strip().lower()
    staged_deferred = bool(metadata.get("staged_ingestion_deferred")) or extraction_method == "deferred"

    if not normalized_body:
        return True
    if normalized_title and normalized_body_lower in {normalized_title, f"{normalized_title}.", f"{normalized_title} ."}:
        return True
    if looks_like_website_shell_text(normalized_body):
        return True

    line_count = len([line for line in str(body_text or "").splitlines() if line.strip()])
    if not staged_deferred:
        return False

    if len(normalized_body) < 400:
        return True
    if line_count <= 4 and len(normalized_body) < 900:
        return True
    if len(normalized_body_lower.replace(normalized_title, "").strip()) < 160:
        return True
    return False


def looks_like_stale_extraction_artifact(
    *,
    body_text: str,
    metadata: dict[str, object],
) -> bool:
    extraction_summary = (
        metadata.get("extraction_summary")
        if isinstance(metadata.get("extraction_summary"), dict)
        else {}
    )

    def _coerce_int(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    normalized_body = re.sub(r"\s+", " ", str(body_text or "")).strip()
    line_count = len([line for line in str(body_text or "").splitlines() if line.strip()])
    source_file_path = str(metadata.get("source_file_path") or "").strip()
    pdf_present = bool(metadata.get("pdf_present")) or source_file_path.lower().endswith(".pdf")
    if not pdf_present:
        return False

    extraction_method = str(
        extraction_summary.get("extraction_method")
        or metadata.get("pdf_extraction_method")
        or metadata.get("extraction_method")
        or ""
    ).strip().lower()
    page_count = _coerce_int(extraction_summary.get("page_count") or metadata.get("page_count"))
    extracted_page_count = _coerce_int(
        extraction_summary.get("extracted_page_count") or metadata.get("extracted_page_count")
    )
    paragraph_count = _coerce_int(extraction_summary.get("paragraph_count") or metadata.get("paragraph_count"))
    heading_count = _coerce_int(extraction_summary.get("heading_count") or metadata.get("heading_count"))

    if extraction_method == "deferred":
        return True

    if extraction_method in {"none", "unknown"} and len(normalized_body) < 1200 and line_count <= 12:
        return True

    if (
        page_count <= 1
        and extracted_page_count <= 1
        and paragraph_count <= 2
        and heading_count <= 1
        and len(normalized_body) < 2500
        and line_count <= 20
    ):
        return True

    return False


def citation_context_excerpt(text: str, needle: str, *, radius: int = 220) -> str:
    source_text = str(text or "")
    target = str(needle or "").strip()
    if not source_text or not target:
        return ""
    pattern = re.compile(re.escape(target), re.IGNORECASE)
    match = pattern.search(source_text)
    if match is None:
        compact_source = re.sub(r"\s+", " ", source_text)
        compact_target = re.sub(r"\s+", " ", target)
        pattern = re.compile(re.escape(compact_target), re.IGNORECASE)
        match = pattern.search(compact_source)
        if match is None:
            return compact_source[: radius * 2].strip()
        start = max(0, match.start() - radius)
        end = min(len(compact_source), match.end() + radius)
        return compact_source[start:end].strip()
    start = max(0, match.start() - radius)
    end = min(len(source_text), match.end() + radius)
    return re.sub(r"\s+", " ", source_text[start:end]).strip()


def infer_year_from_text(text: str) -> int | None:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", str(text or ""))
    if not match:
        return None
    try:
        return int(match.group(1))
    except (TypeError, ValueError):
        return None


def combine_corpus_network_graphs(
    *,
    canonical_graph: dict[str, object],
    crawler_graph: dict[str, object],
) -> dict[str, object]:
    nodes_by_id: dict[str, dict[str, object]] = {}
    for graph in (crawler_graph, canonical_graph):
        for node in graph.get("nodes", []) if isinstance(graph.get("nodes"), list) else []:
            if not isinstance(node, dict):
                continue
            node_id = str(node.get("document_id") or node.get("id") or "").strip()
            if not node_id:
                continue
            existing = nodes_by_id.get(node_id, {})
            nodes_by_id[node_id] = {**existing, **node}

    edge_map: dict[tuple[str, str, str, str], dict[str, object]] = {}
    for source_name, graph in (("crawler_evidence", crawler_graph), ("canonical", canonical_graph)):
        for edge in graph.get("edges", []) if isinstance(graph.get("edges"), list) else []:
            if not isinstance(edge, dict):
                continue
            source = str(edge.get("source") or "").strip()
            target = str(edge.get("target") or "").strip()
            relation = str(edge.get("relation") or "").strip()
            if not source or not target or not relation:
                continue
            key = (source, target, relation, source_name)
            metadata = edge.get("metadata") if isinstance(edge.get("metadata"), dict) else {}
            edge_map[key] = {
                **edge,
                "metadata": {
                    **metadata,
                    "graph_mode": "combined_diagnostic",
                    "diagnostic_source": source_name,
                },
            }

    edge_counts: dict[str, int] = {}
    connected_ids: set[str] = set()
    for edge in edge_map.values():
        relation = str(edge.get("relation") or "")
        edge_counts[relation] = edge_counts.get(relation, 0) + 1
        connected_ids.add(str(edge.get("source") or ""))
        connected_ids.add(str(edge.get("target") or ""))

    nodes = list(nodes_by_id.values())
    connected_count = len({node_id for node_id in connected_ids if node_id in nodes_by_id})
    return {
        "nodes": nodes,
        "edges": list(edge_map.values()),
        "graph_mode": "combined_diagnostic",
        "summary": {
            "graph_mode": "combined_diagnostic",
            "documents_total": len(nodes),
            "connected_documents": connected_count,
            "isolated_documents": max(0, len(nodes) - connected_count),
            "edge_counts": edge_counts,
            "canonical_edges": len(canonical_graph.get("edges", [])) if isinstance(canonical_graph.get("edges"), list) else 0,
            "crawler_evidence_edges": len(crawler_graph.get("edges", [])) if isinstance(crawler_graph.get("edges"), list) else 0,
        },
    }

