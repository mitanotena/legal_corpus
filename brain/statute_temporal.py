from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date
import json
import re
from typing import Any


@dataclass(frozen=True, slots=True)
class TemporalResolutionResult:
    canonical_act_id: str
    act_title: str
    canonical_section_id: str
    section_ref: str
    normalized_section_ref: str
    section_version_id: str
    text_en: str
    valid_from: str | None
    valid_to: str | None
    is_current_version: bool
    operative_date: str | None
    resolution_basis: str
    commencement_instrument: str | None = None
    transitional_note: str | None = None
    is_act_level_or_section_level: str = "unknown"
    warning: str | None = None
    source_start_char: int | None = None
    source_end_char: int | None = None
    source_text_sha256: str | None = None
    cleaned_section_sha256: str | None = None
    source_integrity_status: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["active_section_version_id"] = self.section_version_id
        return payload


def normalize_statute_name(value: object) -> str:
    text = re.sub(r"\s+", " ", str(value or "").strip().lower())
    text = re.sub(r"\b(the|cap\.?\s*\d+[a-z]?)\b", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def normalize_section_number(value: object) -> str:
    text = re.sub(r"\s+", "", str(value or "").strip().lower())
    return re.sub(r"^section", "", text)


def statute_names_compatible(query_name: str, candidate_name: str) -> bool:
    if not query_name or not candidate_name:
        return False
    if query_name == candidate_name:
        return True
    if query_name in candidate_name or candidate_name in query_name:
        return True
    query_tokens = {token for token in re.split(r"[^a-z0-9]+", query_name) if len(token) > 2}
    candidate_tokens = {token for token in re.split(r"[^a-z0-9]+", candidate_name) if len(token) > 2}
    if not query_tokens or not candidate_tokens:
        return False
    return len(query_tokens & candidate_tokens) / max(1, len(query_tokens)) >= 0.6


def resolve_cited_statute_section_temporal(
    conn: Any,
    *,
    act_name: object,
    section_number: object,
    operative_date: str | None = None,
) -> dict[str, Any] | None:
    normalized_act = normalize_statute_name(act_name)
    normalized_section = normalize_section_number(section_number)
    if not normalized_act or not normalized_section:
        return None
    integrity_columns = _integrity_select_columns(conn)
    rows = conn.execute(
        f"""
        SELECT
            a.id AS canonical_act_id,
            COALESCE(a.title, a.label, a.id) AS act_title,
            s.id AS canonical_section_id,
            s.section_ref,
            s.normalized_section_ref,
            v.id AS section_version_id,
            v.text_en,
            v.valid_from,
            v.valid_to,
            v.is_current_version,
            v.metadata_json
            {integrity_columns}
        FROM canonical_acts a
        INNER JOIN canonical_sections s ON s.canonical_act_id = a.id
        LEFT JOIN canonical_section_versions v ON v.canonical_section_id = s.id
        WHERE s.normalized_section_ref = ?
        ORDER BY CASE
            WHEN lower(COALESCE(a.title, a.label, a.id)) = ? THEN 0
            WHEN lower(COALESCE(a.title, a.label, a.id)) LIKE ? THEN 1
            WHEN lower(COALESCE(a.title, a.label, a.id)) LIKE ? THEN 2
            ELSE 9
        END ASC,
        v.is_current_version DESC,
        v.valid_from DESC
        LIMIT 50
        """,
        (normalized_section, normalized_act, f"%{normalized_act}%", f"%{normalized_act.split()[0]}%"),
    ).fetchall()
    candidates = [dict(row) for row in rows if statute_names_compatible(normalized_act, normalize_statute_name(row["act_title"]))]
    return select_temporal_section_version(candidates, operative_date=operative_date)


def select_temporal_section_version(
    candidates: list[dict[str, Any]],
    *,
    operative_date: str | None,
) -> dict[str, Any] | None:
    if not candidates:
        return None
    parsed_date = parse_iso_date(operative_date)
    versioned = [candidate for candidate in candidates if str(candidate.get("section_version_id") or "").strip()]
    if not versioned:
        return _result_from_candidate(candidates[0], operative_date=operative_date, basis="section_without_version", warning="No section-version text exists for this section.")
    selected: dict[str, Any] | None = None
    basis = "current_version"
    warning: str | None = None
    if parsed_date is not None:
        for candidate in versioned:
            valid_from = parse_iso_date(candidate.get("valid_from"))
            valid_to = parse_iso_date(candidate.get("valid_to"))
            starts = valid_from is None or valid_from <= parsed_date
            ends = valid_to is None or parsed_date < valid_to
            if starts and ends:
                selected = candidate
                basis = "operative_date"
                break
        if selected is None:
            warning = f"No section version matched operative date {parsed_date.isoformat()}; falling back to current/latest text."
    if selected is None:
        selected = next((candidate for candidate in versioned if bool(candidate.get("is_current_version")) and not candidate.get("valid_to")), None)
    if selected is None:
        selected = sorted(versioned, key=lambda item: str(item.get("valid_from") or ""), reverse=True)[0]
        basis = "latest_available"
    current = next((candidate for candidate in versioned if bool(candidate.get("is_current_version")) and not candidate.get("valid_to")), None)
    if parsed_date is not None and current is not None and selected.get("section_version_id") != current.get("section_version_id"):
        warning = (
            warning
            or f"The cited case relied on the version operative on {parsed_date.isoformat()}. Current text differs or may differ."
        )
    return _result_from_candidate(
        selected,
        operative_date=parsed_date.isoformat() if parsed_date else None,
        basis=basis,
        warning=warning,
    )


def parse_iso_date(value: object) -> date | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _result_from_candidate(
    candidate: dict[str, Any],
    *,
    operative_date: str | None,
    basis: str,
    warning: str | None,
) -> dict[str, Any]:
    metadata = _safe_json(candidate.get("metadata_json"))
    commencement_instrument = _first_text(metadata, "commencement_instrument", "commencementInstrument")
    transitional_note = _first_text(metadata, "transitional_note", "transitionalNote")
    commencement_scope = _first_text(metadata, "commencement_scope", "commencementScope", "commencement_level")
    if not commencement_scope:
        commencement_scope = "section_level" if metadata.get("section_commencement_verified") else "act_level_unverified"
    result = TemporalResolutionResult(
        canonical_act_id=str(candidate.get("canonical_act_id") or "").strip(),
        act_title=str(candidate.get("act_title") or "").strip(),
        canonical_section_id=str(candidate.get("canonical_section_id") or "").strip(),
        section_ref=str(candidate.get("section_ref") or "").strip(),
        normalized_section_ref=str(candidate.get("normalized_section_ref") or "").strip(),
        section_version_id=str(candidate.get("section_version_id") or "").strip(),
        text_en=str(candidate.get("text_en") or "").strip(),
        valid_from=str(candidate.get("valid_from") or "").strip() or None,
        valid_to=str(candidate.get("valid_to") or "").strip() or None,
        is_current_version=bool(candidate.get("is_current_version")),
        operative_date=operative_date,
        resolution_basis=basis,
        commencement_instrument=commencement_instrument or None,
        transitional_note=transitional_note or None,
        is_act_level_or_section_level=commencement_scope,
        warning=warning,
        source_start_char=_int_or_none(candidate.get("source_start_char")),
        source_end_char=_int_or_none(candidate.get("source_end_char")),
        source_text_sha256=str(candidate.get("source_text_sha256") or metadata.get("source_text_sha256") or "").strip() or None,
        cleaned_section_sha256=str(candidate.get("cleaned_section_sha256") or metadata.get("cleaned_section_sha256") or "").strip() or None,
        source_integrity_status=str(candidate.get("source_integrity_status") or metadata.get("source_integrity_status") or "").strip() or None,
        metadata=metadata,
    )
    payload = result.to_dict()
    if commencement_scope == "act_level_unverified":
        payload["commencement_warning"] = "Act-level date; section-specific commencement not verified."
    return payload


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


def _first_text(mapping: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = str(mapping.get(key) or "").strip()
        if value:
            return value
    return ""


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
    return "\n            ".join(fragments)


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
