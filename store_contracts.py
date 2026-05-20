from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any, Protocol
import sqlite3


LEGAL_CORPUS_REQUIRED_TABLES: tuple[str, ...] = (
    "documents",
    "canonical_cases",
    "canonical_acts",
    "canonical_act_versions",
    "canonical_sections",
    "canonical_section_versions",
    "canonical_matters",
    "canonical_aliases",
    "pin_references",
    "legal_edges",
)

LEGAL_CORPUS_CANONICAL_METHODS: tuple[str, ...] = (
    "connect",
    "init_schema",
    "upsert_canonical_case",
    "upsert_canonical_act",
    "upsert_canonical_act_version",
    "upsert_canonical_section",
    "upsert_canonical_section_version",
    "upsert_legal_edge",
    "get_canonical_node",
    "resolve_authority_reference",
    "resolve_statute_authority",
    "get_current_section_text",
)


class LegalCorpusStore(Protocol):
    db_path: Any

    def connect(self) -> AbstractContextManager[sqlite3.Connection]:
        ...

    def init_schema(self) -> None:
        ...

    def upsert_canonical_case(
        self,
        *,
        canonical_case_id: str,
        label: str,
        canonical_citation: str | None,
        title: str | None,
        source_document_id: str | None,
        jurisdiction: str | None,
        court: str | None,
        year: int | None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        ...

    def upsert_canonical_act(
        self,
        *,
        canonical_act_id: str,
        canonical_statute_id: str | None,
        label: str,
        title: str | None,
        citation: str | None,
        source_document_id: str | None,
        jurisdiction: str | None,
        year: int | None,
        is_current_version: bool,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        ...

    def upsert_canonical_act_version(
        self,
        *,
        canonical_act_id: str,
        source_document_id: str,
        citation: str | None,
        title: str | None,
        year: int | None,
        is_current_version: bool,
        supersedes_document_id: str | None,
        amends_document_id: str | None,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        ...

    def upsert_canonical_section(
        self,
        *,
        canonical_act_id: str,
        canonical_statute_id: str | None,
        section_ref: str,
        label: str,
        source_document_id: str | None,
        section_kind: str = "section",
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object] | None:
        ...

    def upsert_canonical_section_version(
        self,
        *,
        canonical_section_id: str,
        canonical_act_id: str,
        section_number: str,
        text_en: str,
        text_sw: str | None,
        valid_from: str,
        valid_to: str | None,
        is_current_version: bool,
        metadata: dict[str, object] | None = None,
    ) -> dict[str, object]:
        ...

    def upsert_legal_edge(
        self,
        *,
        edge_type: str,
        source_node_id: str,
        source_node_type: str,
        target_node_id: str,
        target_node_type: str,
        confidence: float | None = None,
        status: str = "active",
        valid_from: str | None = None,
        valid_to: str | None = None,
        replaced_by_edge_id: str | None = None,
        provenance: dict[str, object] | None = None,
        evidence: dict[str, object] | None = None,
    ) -> dict[str, object]:
        ...

    def get_canonical_node(self, node_id: str) -> dict[str, object] | None:
        ...

    def resolve_authority_reference(
        self,
        reference: str,
        *,
        current_document_id: str | None = None,
        context: str | None = None,
    ) -> dict[str, object]:
        ...

    def resolve_statute_authority(self, canonical_statute_id: str) -> dict[str, object] | None:
        ...

    def get_current_section_text(self, section_id: str) -> dict[str, object]:
        ...


def validate_legal_corpus_store_contract(store: object) -> list[str]:
    missing: list[str] = []
    for method_name in LEGAL_CORPUS_CANONICAL_METHODS:
        if not callable(getattr(store, method_name, None)):
            missing.append(method_name)
    return missing

