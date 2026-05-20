from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
from typing import Any


@dataclass(frozen=True, slots=True)
class StatuteTextIntegrityResult:
    ok: bool
    status: str
    text_en: str
    warning: str | None = None
    cleaned_section_sha256: str | None = None
    recomputed_text_sha256: str | None = None
    source_text_sha256: str | None = None
    source_start_char: int | None = None
    source_end_char: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def sha256_text(value: object) -> str:
    return hashlib.sha256(str(value or "").encode("utf-8")).hexdigest()


def verify_section_text_integrity(row: dict[str, Any]) -> StatuteTextIntegrityResult:
    text_en = str(row.get("text_en") or "")
    cleaned_section_sha256 = _first_text(row, "cleaned_section_sha256")
    source_text_sha256 = _first_text(row, "source_text_sha256")
    source_start_char = _int_or_none(row.get("source_start_char"))
    source_end_char = _int_or_none(row.get("source_end_char"))
    recomputed = sha256_text(text_en)

    if not text_en.strip():
        return StatuteTextIntegrityResult(
            ok=False,
            status="source_integrity_unverified",
            text_en="",
            warning="Statutory text was not injected because section text is empty.",
            cleaned_section_sha256=cleaned_section_sha256 or None,
            recomputed_text_sha256=recomputed,
            source_text_sha256=source_text_sha256 or None,
            source_start_char=source_start_char,
            source_end_char=source_end_char,
        )
    if not cleaned_section_sha256:
        return StatuteTextIntegrityResult(
            ok=False,
            status="source_integrity_unverified",
            text_en="",
            warning="Statutory text was not injected because no section-level hash exists. Backfill source integrity before quoting verbatim.",
            cleaned_section_sha256=None,
            recomputed_text_sha256=recomputed,
            source_text_sha256=source_text_sha256 or None,
            source_start_char=source_start_char,
            source_end_char=source_end_char,
        )
    if cleaned_section_sha256 != recomputed:
        return StatuteTextIntegrityResult(
            ok=False,
            status="hash_verification_failed",
            text_en="",
            warning="Statutory text was not injected because stored section hash does not match text_en.",
            cleaned_section_sha256=cleaned_section_sha256,
            recomputed_text_sha256=recomputed,
            source_text_sha256=source_text_sha256 or None,
            source_start_char=source_start_char,
            source_end_char=source_end_char,
        )
    if not source_text_sha256 or source_start_char is None or source_end_char is None or source_end_char <= source_start_char:
        return StatuteTextIntegrityResult(
            ok=False,
            status="source_integrity_unverified",
            text_en="",
            warning="Statutory text was not injected because source offsets or source-text hash are missing.",
            cleaned_section_sha256=cleaned_section_sha256,
            recomputed_text_sha256=recomputed,
            source_text_sha256=source_text_sha256 or None,
            source_start_char=source_start_char,
            source_end_char=source_end_char,
        )
    return StatuteTextIntegrityResult(
        ok=True,
        status="verified",
        text_en=text_en,
        cleaned_section_sha256=cleaned_section_sha256,
        recomputed_text_sha256=recomputed,
        source_text_sha256=source_text_sha256,
        source_start_char=source_start_char,
        source_end_char=source_end_char,
    )


def _first_text(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if value:
        return value
    metadata = row.get("metadata")
    if isinstance(metadata, dict):
        return str(metadata.get(key) or "").strip()
    return ""


def _int_or_none(value: object) -> int | None:
    try:
        return int(str(value).strip())
    except (TypeError, ValueError):
        return None
