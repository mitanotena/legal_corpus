from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import sqlite3
from typing import Any, Literal
import uuid


RefusalSeverity = Literal["info", "warning", "blocker"]


class RefusalReason(StrEnum):
    IRAC_CONTRACT_FAILED = "IRAC_CONTRACT_FAILED"
    CREAC_CONTRACT_FAILED = "CREAC_CONTRACT_FAILED"
    ANSWER_TYPE_CONTRACT_FAILED = "ANSWER_TYPE_CONTRACT_FAILED"
    BURDEN_UNKNOWN = "BURDEN_UNKNOWN"
    STANDARD_UNKNOWN = "STANDARD_UNKNOWN"
    TEMPORAL_MISMATCH = "TEMPORAL_MISMATCH"
    HASH_VERIFICATION_FAILED = "HASH_VERIFICATION_FAILED"
    CITATION_UNVERIFIED = "CITATION_UNVERIFIED"
    AUTHORITY_SUPPRESSED = "AUTHORITY_SUPPRESSED"
    OBITER_AS_BINDING_BLOCKED = "OBITER_AS_BINDING_BLOCKED"
    STARE_DECISIS_CONFLICT = "STARE_DECISIS_CONFLICT"
    ELEMENT_APPLICATION_MISSING = "ELEMENT_APPLICATION_MISSING"
    JURISDICTION_UNSAFE = "JURISDICTION_UNSAFE"
    INSUFFICIENT_CORPUS_EVIDENCE = "INSUFFICIENT_CORPUS_EVIDENCE"


REFUSAL_RATE_ALERT_THRESHOLD = 0.05


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def hash_query_identifier(value: str) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    if not normalized:
        return ""
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class RefusalEvent:
    reason: RefusalReason
    query_id: str
    source_component: str
    fallback_used: bool
    partial_answer: bool
    severity: RefusalSeverity = "warning"
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=utc_now_iso)
    matter_id_hash: str | None = None
    interaction_id: str | None = None
    message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_record(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason"] = self.reason.value
        payload["metadata_json"] = json.dumps(self.metadata, ensure_ascii=True, sort_keys=True)
        payload.pop("metadata", None)
        return payload


def ensure_refusal_events_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS legal_refusal_events (
            event_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            reason TEXT NOT NULL,
            severity TEXT NOT NULL,
            query_id TEXT NOT NULL,
            matter_id_hash TEXT,
            interaction_id TEXT,
            source_component TEXT NOT NULL,
            fallback_used INTEGER NOT NULL,
            partial_answer INTEGER NOT NULL,
            message TEXT,
            metadata_json TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_legal_refusal_events_created_reason
        ON legal_refusal_events(created_at, reason)
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_legal_refusal_events_query
        ON legal_refusal_events(query_id, created_at)
        """
    )


def record_refusal_event(conn: sqlite3.Connection, event: RefusalEvent) -> dict[str, Any]:
    ensure_refusal_events_table(conn)
    record = event.to_record()
    conn.execute(
        """
        INSERT INTO legal_refusal_events (
            event_id,
            created_at,
            reason,
            severity,
            query_id,
            matter_id_hash,
            interaction_id,
            source_component,
            fallback_used,
            partial_answer,
            message,
            metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(event_id) DO NOTHING
        """,
        (
            record["event_id"],
            record["created_at"],
            record["reason"],
            record["severity"],
            record["query_id"],
            record["matter_id_hash"],
            record["interaction_id"],
            record["source_component"],
            1 if record["fallback_used"] else 0,
            1 if record["partial_answer"] else 0,
            record["message"],
            record["metadata_json"],
        ),
    )
    return record


def list_refusal_events(
    conn: sqlite3.Connection,
    *,
    limit: int = 100,
    reason: RefusalReason | None = None,
) -> list[dict[str, Any]]:
    ensure_refusal_events_table(conn)
    bounded_limit = max(1, min(1000, int(limit)))
    params: list[Any] = []
    where_clause = ""
    if reason is not None:
        where_clause = "WHERE reason = ?"
        params.append(reason.value)
    rows = conn.execute(
        f"""
        SELECT *
        FROM legal_refusal_events
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ?
        """,
        (*params, bounded_limit),
    ).fetchall()
    return [_row_to_dict(row) for row in rows]


def refusal_rate(
    conn: sqlite3.Connection,
    *,
    total_answer_count: int,
    since_iso: str | None = None,
) -> float:
    ensure_refusal_events_table(conn)
    if total_answer_count <= 0:
        return 0.0
    params: tuple[Any, ...]
    where_clause = ""
    if since_iso:
        where_clause = "WHERE created_at >= ?"
        params = (since_iso,)
    else:
        params = ()
    row = conn.execute(
        f"""
        SELECT COUNT(*) AS refusal_count
        FROM legal_refusal_events
        {where_clause}
        """,
        params,
    ).fetchone()
    refusal_count = int(row["refusal_count"] if isinstance(row, sqlite3.Row) else row[0])
    return refusal_count / max(1, int(total_answer_count))


def refusal_rate_alert(
    conn: sqlite3.Connection,
    *,
    total_answer_count: int,
    since_iso: str | None = None,
    threshold: float = REFUSAL_RATE_ALERT_THRESHOLD,
) -> dict[str, Any]:
    rate = refusal_rate(conn, total_answer_count=total_answer_count, since_iso=since_iso)
    return {
        "alert": bool(rate > float(threshold)),
        "rate": rate,
        "threshold": float(threshold),
        "totalAnswerCount": max(0, int(total_answer_count)),
    }


def _row_to_dict(row: sqlite3.Row | tuple[Any, ...]) -> dict[str, Any]:
    if isinstance(row, sqlite3.Row):
        item = dict(row)
    else:
        keys = (
            "event_id",
            "created_at",
            "reason",
            "severity",
            "query_id",
            "matter_id_hash",
            "interaction_id",
            "source_component",
            "fallback_used",
            "partial_answer",
            "message",
            "metadata_json",
        )
        item = dict(zip(keys, row, strict=False))
    try:
        item["metadata"] = json.loads(str(item.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        item["metadata"] = {}
    item["fallback_used"] = bool(item.get("fallback_used"))
    item["partial_answer"] = bool(item.get("partial_answer"))
    return item

