from __future__ import annotations

from copy import deepcopy
from typing import Any

ONTOLOGY_VERSION = "1.2.0"

TANZANIA_JURISDICTIONS = {"mainland", "zanzibar", "union"}
JURISDICTION_REQUIRED_NODE_TYPES = {
    "Act",
    "ActVersion",
    "Case",
    "Court",
    "Judgment",
    "Matter",
    "SectionVersion",
}

NODE_TYPES: dict[str, dict[str, Any]] = {
    "Case": {
        "description": "A canonical case identity that may be represented by one or more judgment source documents.",
        "required_properties": ["canonical_id", "label", "court_level", "procedural_posture", "language"],
        "optional_properties": ["canonical_citation", "jurisdiction", "court", "year", "panel_size", "decision_date"],
        "source_of_truth": [
            "documents where document_type='judgment'",
            "citations where is_primary_document_citation=1",
        ],
    },
    "Document": {
        "description": "A generic legal document root used when a crawled record is not yet classified into a narrower legal type.",
        "required_properties": ["document_id", "title", "document_type", "source_name", "court_level", "procedural_posture", "language"],
        "optional_properties": [
            "citation",
            "jurisdiction",
            "language",
            "publication_date",
        ],
        "source_of_truth": [
            "documents",
        ],
    },
    "Judgment": {
        "description": "A decided case or ruling from a court or tribunal.",
        "required_properties": ["document_id", "title", "document_type", "source_name"],
        "optional_properties": [
            "citation",
            "canonical_citation",
            "case_number",
            "court",
            "court_level",
            "judgment_date",
            "decision_date",
            "publication_date",
            "jurisdiction",
            "language",
            "panel_size",
        ],
        "source_of_truth": [
            "documents where document_type='judgment'",
            "document_judgment_metadata",
        ],
    },
    "Act": {
        "description": "A principal Act or revised Act in force or historical form.",
        "required_properties": ["document_id", "title", "document_type", "source_name"],
        "optional_properties": [
            "citation",
            "canonical_statute_id",
            "year",
            "jurisdiction",
            "is_current_version",
            "publication_date",
        ],
        "source_of_truth": [
            "documents where document_type='act'",
            "act_consolidations",
        ],
    },
    "ActVersion": {
        "description": "A concrete version of an Act tied to a specific source document and lifecycle state.",
        "required_properties": ["document_id", "label", "version_string", "valid_from", "is_current"],
        "optional_properties": [
            "citation",
            "year",
            "is_current_version",
            "version_string",
            "supersedes_document_id",
            "amends_document_id",
            "valid_from",
            "valid_to",
        ],
        "source_of_truth": [
            "documents where document_type in ('act', 'amendment')",
            "canonical_act_versions",
        ],
    },
    "Amendment": {
        "description": "An amending Act or other amendment instrument linked to a base Act.",
        "required_properties": ["document_id", "title", "document_type", "source_name"],
        "optional_properties": [
            "citation",
            "year",
            "jurisdiction",
            "publication_date",
            "is_current_version",
            "amends_document_id",
            "supersedes_document_id",
        ],
        "source_of_truth": [
            "documents where document_type='amendment'",
            "crawler_amendment_review_queue",
        ],
    },
    "Section": {
        "description": "A numbered or labeled substantive unit in an Act, regulation, or consolidated text.",
        "required_properties": ["label", "section_kind"],
        "optional_properties": [
            "part_label",
            "sub_part_label",
            "target_law_title",
            "page_number",
        ],
        "source_of_truth": [
            "document_paragraphs.section_heading",
            "document_chunks.section_label",
            "act_consolidations.consolidated_text",
        ],
    },
    "SectionVersion": {
        "description": "A concrete version of a section with temporal validity.",
        "required_properties": ["section_number", "text_en", "valid_from", "is_current"],
        "optional_properties": ["text_sw", "valid_to", "canonical_section_id", "canonical_act_id"],
        "source_of_truth": [
            "canonical_sections",
            "act_consolidations",
        ],
    },
    "ExternalAuthority": {
        "description": "A contextual non-canonical authority reference for lower-court signals.",
        "required_properties": ["label", "authority_kind"],
        "optional_properties": ["citation", "court", "year", "jurisdiction", "binding_strength"],
        "source_of_truth": [
            "authority resolution fallback",
            "operator curation",
        ],
    },
    "Court": {
        "description": "A court or tribunal whose hierarchy and jurisdiction govern legal authority weight.",
        "required_properties": ["name"],
        "optional_properties": ["court_level", "jurisdiction", "division", "location", "source"],
        "source_of_truth": [
            "documents.court",
            "document_judgment_metadata",
            "operator curation",
        ],
    },
    "JudicialPanel": {
        "description": "A bench or panel that heard or decided a case.",
        "required_properties": ["label"],
        "optional_properties": ["court", "court_level", "panel_size", "jurisdiction", "decision_date"],
        "source_of_truth": [
            "document_judgment_metadata.normalized_judge_panel_json",
            "judgment_judge_links",
        ],
    },
    "LegalRole": {
        "description": "A controlled role concept such as plaintiff, defendant, witness, advocate, appellant, or respondent.",
        "required_properties": ["label"],
        "optional_properties": ["role_code", "role_family", "language", "sw_label"],
        "source_of_truth": [
            "controlled vocabulary",
            "matter intake",
            "document_judgment_metadata.parties_json",
        ],
    },
    "LegalParticipation": {
        "description": "A time-scoped participation record linking an actor, role, and case or matter without making the role permanent identity.",
        "required_properties": ["participation_id", "role"],
        "optional_properties": [
            "actor_node_id",
            "case_node_id",
            "matter_node_id",
            "role_start_date",
            "role_end_date",
            "jurisdiction",
            "provenance",
        ],
        "source_of_truth": [
            "matter parties",
            "document_judgment_metadata.parties_json",
            "conflict check intake",
        ],
    },
    "Regulation": {
        "description": "A regulation or rule unit inside subsidiary legislation.",
        "required_properties": ["label", "section_kind"],
        "optional_properties": ["page_number", "target_law_title"],
        "source_of_truth": [
            "document_paragraphs.section_heading",
            "document_chunks.section_label",
        ],
    },
    "Schedule": {
        "description": "A schedule, table, or annexure attached to an Act or subsidiary instrument.",
        "required_properties": ["label", "section_kind"],
        "optional_properties": ["page_number", "contains_table_like"],
        "source_of_truth": [
            "document_paragraphs.section_heading",
            "document_chunks.section_label",
        ],
    },
    "Party": {
        "description": "A litigating party or named actor in a judgment.",
        "required_properties": ["name"],
        "optional_properties": ["role", "position", "party_type", "alias"],
        "source_of_truth": [
            "document_judgment_metadata.parties_json",
            "document_entities where entity_type='party'",
        ],
    },
    "Matter": {
        "description": "A matter-scoped working graph root used by Wakili research, drafting, and authority review flows.",
        "required_properties": ["matter_id", "label"],
        "optional_properties": ["matter_number", "jurisdiction", "status", "practice_area"],
        "source_of_truth": [
            "matter_store",
        ],
    },
    "PinReference": {
        "description": "A canonical citation pin for page, paragraph, section, or chunk anchors inside a legal authority.",
        "required_properties": ["document_id"],
        "optional_properties": ["page", "paragraph", "section", "chunk_index"],
        "source_of_truth": [
            "document_chunks",
            "document_paragraphs",
            "authority resolution pin metadata",
        ],
    },
    "Judge": {
        "description": "A judge or judicial panel member associated with a judgment.",
        "required_properties": ["name"],
        "optional_properties": ["title", "confidence"],
        "source_of_truth": [
            "document_judgment_metadata.judge_name",
            "document_judgment_metadata.normalized_judge_panel_json",
            "document_entities where entity_type='judge'",
        ],
    },
    "Issue": {
        "description": "A framed legal issue or question for determination in a judgment.",
        "required_properties": ["text"],
        "optional_properties": ["confidence", "issue_index"],
        "source_of_truth": [
            "document_judgment_metadata.issues_framed_json",
        ],
    },
    "Fact": {
        "description": "A material fact point extracted from the factual background of a judgment.",
        "required_properties": ["text"],
        "optional_properties": ["fact_index", "confidence"],
        "source_of_truth": [
            "document_judgment_metadata.fact_points_json",
        ],
    },
    "Holding": {
        "description": "A holding or finding tied to a judgment issue or disposition.",
        "required_properties": ["text"],
        "optional_properties": ["issue_index", "basis", "confidence"],
        "source_of_truth": [
            "document_judgment_metadata.holdings_json",
            "document_judgment_metadata.structured_outcomes_json",
        ],
    },
    "Ratio": {
        "description": "A ratio decidendi reasoning segment that supports the doctrinal basis of the judgment.",
        "required_properties": ["text"],
        "optional_properties": ["segment_index", "confidence"],
        "source_of_truth": [
            "document_judgment_metadata.ratio_segments_json",
        ],
    },
    "Obiter": {
        "description": "An obiter dicta segment that provides persuasive but non-binding reasoning.",
        "required_properties": ["text"],
        "optional_properties": ["segment_index", "confidence"],
        "source_of_truth": [
            "document_judgment_metadata.obiter_segments_json",
        ],
    },
    "Order": {
        "description": "A relief, order, or disposition issued by the court.",
        "required_properties": ["text"],
        "optional_properties": ["relief", "against", "amount", "currency", "confidence"],
        "source_of_truth": [
            "document_judgment_metadata.orders_json",
            "document_judgment_metadata.structured_outcomes_json",
        ],
    },
    "Right": {
        "description": "A deontic right recognized or explained in legal reasoning.",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name", "grounded_statute_node_id"],
        "source_of_truth": [
            "document_judgment_metadata.deontic_annotations_json where annotation_type='right'",
        ],
    },
    "Duty": {
        "description": "A deontic duty or mandatory obligation extracted from legal reasoning.",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name", "grounded_statute_node_id"],
        "source_of_truth": [
            "document_judgment_metadata.deontic_annotations_json where annotation_type='duty'",
        ],
    },
    "Prohibition": {
        "description": "A prohibition or negative command extracted from legal reasoning.",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name", "grounded_statute_node_id"],
        "source_of_truth": [
            "document_judgment_metadata.deontic_annotations_json where annotation_type='prohibition'",
        ],
    },
    "Exception": {
        "description": "A legal exception or carve-out extracted from legal reasoning.",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name", "grounded_statute_node_id"],
        "source_of_truth": [
            "document_judgment_metadata.deontic_annotations_json where annotation_type='exception'",
        ],
    },
    "Power": {
        "description": "A legal power or discretionary authority extracted from legal reasoning.",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name", "grounded_statute_node_id"],
        "source_of_truth": [
            "document_judgment_metadata.deontic_annotations_json where annotation_type='power'",
        ],
    },
    "Citation": {
        "description": "A cited case, statute, or external authority reference.",
        "required_properties": ["citation_text", "citation_type"],
        "optional_properties": [
            "canonical_citation",
            "canonical_statute_id",
            "linked_document_id",
            "target_kind",
            "treatment_type",
        ],
        "source_of_truth": [
            "document_citation_links",
            "citations",
        ],
    },
    "StatuteReference": {
        "description": "A structured statute mention extracted from a document.",
        "required_properties": ["act_name"],
        "optional_properties": ["section_ref", "instrument_ref", "canonical_statute_id", "revision_year"],
        "source_of_truth": [
            "document_structured_statutes",
        ],
    },
    "AmendmentOperation": {
        "description": "A concrete amendment instruction against a base Act.",
        "required_properties": ["operation_type", "sequence_no"],
        "optional_properties": [
            "target_section",
            "target_anchor",
            "new_section_label",
            "replacement_text",
            "confidence",
        ],
        "source_of_truth": [
            "act_amendment_operations",
        ],
    },
    "TemporalMarker": {
        "description": "A date-bearing temporal marker used to reason about judgment timing and legislative validity.",
        "required_properties": ["date_type", "date_value"],
        "optional_properties": ["source_field"],
        "source_of_truth": [
            "documents.publication_date",
            "documents.metadata_json",
            "document_judgment_metadata.true_judgment_date",
        ],
    },
    "LegalConcept": {
        "description": "A normalized legal doctrine, issue, or concept used to connect lawyer language to graph retrieval.",
        "required_properties": ["canonical_key", "pref_label_en", "doctrine_area", "jurisdiction_scope"],
        "optional_properties": ["pref_label_sw", "definition", "source_authority", "status"],
        "source_of_truth": ["legal_concepts", "ontology/legal_ontology.ttl"],
    },
    "ConceptAlias": {
        "description": "A language-specific synonym or phrase that resolves to a canonical legal concept.",
        "required_properties": ["alias", "alias_normalized", "language"],
        "optional_properties": ["alias_type", "confidence"],
        "source_of_truth": ["legal_concept_aliases"],
    },
    "LegalTest": {
        "description": "A doctrinal test with elements that can be satisfied or failed by case facts.",
        "required_properties": ["test_id", "label", "jurisdiction"],
        "optional_properties": ["concept_id", "source_authority", "temporal_gate"],
        "source_of_truth": ["controlled legal concept vocabulary", "master judgment extraction payload"],
    },
    "ClaimElement": {
        "description": "A required element of a legal test, claim, defence, or cause of action.",
        "required_properties": ["element_id", "label"],
        "optional_properties": ["sequence_no", "burden", "temporal_gate"],
        "source_of_truth": ["controlled legal concept vocabulary", "master judgment extraction payload"],
    },
    "BurdenOfProof": {
        "description": "A matter-scoped burden allocation for a party or legal element.",
        "required_properties": ["burden_id", "allocated_to"],
        "optional_properties": ["standard_id", "source_reference", "confidence"],
        "source_of_truth": ["master judgment extraction payload"],
    },
    "StandardOfProof": {
        "description": "The applicable evidentiary standard for a legal issue or burden.",
        "required_properties": ["standard_id", "label"],
        "optional_properties": ["jurisdiction", "source_authority"],
        "source_of_truth": ["controlled legal concept vocabulary", "master judgment extraction payload"],
    },
    "LegalOutcome": {
        "description": "The legal result of applying a test or deciding an issue.",
        "required_properties": ["outcome_id", "label"],
        "optional_properties": ["disposition", "relief", "confidence"],
        "source_of_truth": ["master judgment extraction payload", "document_judgment_metadata.structured_outcomes_json"],
    },
    "AuthorityStatus": {
        "description": "A materialized issue-scoped good-law status for a legal authority.",
        "required_properties": ["status", "confidence", "ontology_version"],
        "optional_properties": [
            "case_id",
            "issue_id",
            "legal_concept_id",
            "status_reason",
            "controlling_case_id",
            "binding_weight",
            "persuasive_weight",
            "provenance",
        ],
        "source_of_truth": ["case_authority_status", "deterministic authority status materializer"],
    },
    "LegalConflict": {
        "description": "A possible or confirmed contradiction between authorities on an issue, statute section, or legal concept.",
        "required_properties": ["conflict_id", "status", "confidence"],
        "optional_properties": ["issue_id", "legal_concept_id", "source_case_id", "target_case_id", "provenance"],
        "source_of_truth": ["conflict detection materializer", "operator review"],
    },
    "ConflictResolution": {
        "description": "A reviewed or inferred resolution for a legal conflict, such as controlling authority, harmonization, or false positive.",
        "required_properties": ["resolution_id", "resolution_type"],
        "optional_properties": ["resolved_by", "resolved_at", "reason", "provenance"],
        "source_of_truth": ["conflict review queue", "deterministic hierarchy rules"],
    },
    "DistinguishingReason": {
        "description": "A fact, issue, legal principle, jurisdiction, or procedural basis for distinguishing one authority from another.",
        "required_properties": ["reason_id", "reason_type", "text"],
        "optional_properties": ["quote", "source_paragraph", "confidence"],
        "source_of_truth": ["case_treatments", "contradiction_signals", "operator review"],
    },
    "LegalEvent": {
        "description": "A date-bearing legal event relevant to limitation, procedural posture, or authority status.",
        "required_properties": ["event_id", "event_type"],
        "optional_properties": ["event_date", "jurisdiction", "source_document_id", "provenance"],
        "source_of_truth": ["master extraction payload", "statute temporal markers", "matter events"],
    },
    "InterruptionEvent": {
        "description": "A legal event that may interrupt an adverse possession limitation period or similar temporal test.",
        "required_properties": ["event_id", "interruption_type"],
        "optional_properties": ["event_date", "legal_concept_id", "source_paragraph", "confidence"],
        "source_of_truth": ["adverse possession temporal materializer", "master extraction payload"],
    },
    "ExtractionPayload": {
        "description": "Stored raw master extraction output with schema, prompt, ontology, source hash, validation, and provenance metadata.",
        "required_properties": [
            "document_id",
            "extraction_schema_version",
            "static_prompt_hash",
            "ontology_context_hash",
            "source_text_hash",
            "validation_status",
        ],
        "optional_properties": ["extractor_model", "ontology_version", "confidence", "created_at", "review_status"],
        "source_of_truth": ["document_judgment_metadata", "master extraction cache"],
    },
}

RELATIONSHIP_TYPES: dict[str, dict[str, Any]] = {
    "HAS_SOURCE_DOCUMENT": {
        "source": "Case",
        "target": "Document",
        "cardinality": "1:N",
        "required_properties": [],
        "optional_properties": ["confidence"],
        "source_of_truth": ["documents", "citations where is_primary_document_citation=1"],
    },
    "HAS_VERSION": {
        "source": "Act",
        "target": "ActVersion",
        "cardinality": "1:N",
        "required_properties": [],
        "optional_properties": ["confidence"],
        "source_of_truth": ["canonical_act_versions", "documents"],
    },
    "CITES_CASE": {
        "source": ["Matter", "Case"],
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["canonical_citation", "linked_document_id", "treatment_type", "confidence", "source_reference"],
        "source_of_truth": ["document_citation_links where target_kind='case'", "matter interactions", "authority resolution"],
    },
    "CITES_ACT": {
        "source": ["Matter", "Case"],
        "target": "Act",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "source_reference"],
        "source_of_truth": ["matter interactions", "authority resolution", "document_structured_statutes"],
    },
    "CITES_SECTION": {
        "source": ["Matter", "Case"],
        "target": ["Section", "SectionVersion"],
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "source_reference"],
        "source_of_truth": ["matter interactions", "authority resolution", "document_structured_statutes"],
    },
    "APPLIES_SECTION": {
        "source": ["Matter", "Case"],
        "target": ["Section", "SectionVersion"],
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "source_reference", "application_basis"],
        "source_of_truth": ["document_structured_statutes", "judgment treatment extraction"],
    },
    "CITES_STATUTE": {
        "source": "Judgment",
        "target": "StatuteReference",
        "cardinality": "0:N",
        "required_properties": ["act_name"],
        "optional_properties": ["section_ref", "canonical_statute_id", "linked_document_id", "confidence"],
        "source_of_truth": ["document_structured_statutes", "document_citation_links where target_kind='statute'"],
    },
    "DECIDED_BY": {
        "source": ["Case", "Judgment"],
        "target": "Court",
        "cardinality": "1:N",
        "required_properties": [],
        "optional_properties": ["court_name", "court_level", "jurisdiction", "confidence"],
        "source_of_truth": ["documents.court", "document_judgment_metadata"],
    },
    "AUTHORED_BY": {
        "source": "Judgment",
        "target": "Judge",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["judge_name", "judge_title", "role", "confidence"],
        "source_of_truth": ["document_judgment_metadata", "judgment_judge_links"],
    },
    "HEARD_BY_PANEL": {
        "source": ["Case", "Judgment"],
        "target": "JudicialPanel",
        "cardinality": "0:1",
        "required_properties": [],
        "optional_properties": ["panel_size", "confidence"],
        "source_of_truth": ["document_judgment_metadata.normalized_judge_panel_json", "judgment_judge_links"],
    },
    "HAS_PANEL_MEMBER": {
        "source": "JudicialPanel",
        "target": "Judge",
        "cardinality": "1:N",
        "required_properties": [],
        "optional_properties": ["role", "confidence"],
        "source_of_truth": ["document_judgment_metadata.normalized_judge_panel_json", "judgment_judge_links"],
    },
    "HAS_PARTY": {
        "source": "Judgment",
        "target": "Party",
        "cardinality": "1:N",
        "required_properties": ["name", "role"],
        "optional_properties": ["position", "party_type", "alias"],
        "source_of_truth": ["document_judgment_metadata.parties_json"],
    },
    "HAS_ISSUE": {
        "source": "Judgment",
        "target": "Issue",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["issue_index", "confidence"],
        "source_of_truth": ["document_judgment_metadata.issues_framed_json"],
    },
    "HAS_FACT": {
        "source": "Judgment",
        "target": "Fact",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["fact_index", "confidence"],
        "source_of_truth": ["document_judgment_metadata.fact_points_json"],
    },
    "HAS_HOLDING": {
        "source": "Judgment",
        "target": "Holding",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["issue_index", "basis", "confidence"],
        "source_of_truth": ["document_judgment_metadata.holdings_json"],
    },
    "RESOLVES_ISSUE": {
        "source": "Holding",
        "target": "Issue",
        "cardinality": "0:1",
        "required_properties": ["issue_index"],
        "optional_properties": ["confidence"],
        "source_of_truth": ["document_judgment_metadata.holdings_json"],
    },
    "HAS_RATIO": {
        "source": "Judgment",
        "target": "Ratio",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["segment_index", "confidence"],
        "source_of_truth": ["document_judgment_metadata.ratio_segments_json"],
    },
    "HAS_OBITER": {
        "source": "Judgment",
        "target": "Obiter",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["segment_index", "confidence"],
        "source_of_truth": ["document_judgment_metadata.obiter_segments_json"],
    },
    "HAS_ORDER": {
        "source": "Judgment",
        "target": "Order",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["relief", "against", "amount", "currency", "confidence"],
        "source_of_truth": ["document_judgment_metadata.orders_json"],
    },
    "ESTABLISHES_RIGHT": {
        "source": "Judgment",
        "target": "Right",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name"],
        "source_of_truth": ["document_judgment_metadata.deontic_annotations_json where annotation_type='right'"],
    },
    "IMPOSES_DUTY": {
        "source": "Judgment",
        "target": "Duty",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name"],
        "source_of_truth": ["document_judgment_metadata.deontic_annotations_json where annotation_type='duty'"],
    },
    "IMPOSES_PROHIBITION": {
        "source": "Judgment",
        "target": "Prohibition",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name"],
        "source_of_truth": ["document_judgment_metadata.deontic_annotations_json where annotation_type='prohibition'"],
    },
    "HAS_EXCEPTION": {
        "source": "Judgment",
        "target": "Exception",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name"],
        "source_of_truth": ["document_judgment_metadata.deontic_annotations_json where annotation_type='exception'"],
    },
    "CONFERS_POWER": {
        "source": "Judgment",
        "target": "Power",
        "cardinality": "0:N",
        "required_properties": ["text"],
        "optional_properties": ["source", "act_name"],
        "source_of_truth": ["document_judgment_metadata.deontic_annotations_json where annotation_type='power'"],
    },
    "AMENDS": {
        "source": ["Amendment", "ActVersion", "SectionVersion"],
        "target": ["Act", "ActVersion", "SectionVersion"],
        "cardinality": "1:N",
        "required_properties": [],
        "optional_properties": ["confidence", "link_reason"],
        "source_of_truth": ["documents.amends_document_id", "crawler_amendment_review_queue", "act_amendment_operations"],
    },
    "OVERRULES": {
        "source": "Case",
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": ["overruling_reason"],
        "optional_properties": ["confidence", "evidence"],
        "source_of_truth": ["document_doctrinal_edges", "judgment treatment extraction"],
    },
    "REVERSES_ON_APPEAL": {
        "source": "Case",
        "target": ["Case", "ExternalAuthority"],
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "evidence"],
        "source_of_truth": ["document_doctrinal_edges", "judgment treatment extraction"],
    },
    "FOLLOWS": {
        "source": "Case",
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "evidence"],
        "source_of_truth": ["document_doctrinal_edges", "judgment treatment extraction"],
    },
    "DISTINGUISHES": {
        "source": "Case",
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": ["distinguishing_reason"],
        "optional_properties": ["confidence", "evidence", "distinction_type"],
        "source_of_truth": ["document_doctrinal_edges", "judgment treatment extraction"],
    },
    "INTERPRETS_SECTION": {
        "source": ["Case", "Judgment", "Ratio"],
        "target": "SectionVersion",
        "cardinality": "0:N",
        "required_properties": ["interpretation_type", "decision_date"],
        "optional_properties": ["confidence", "evidence"],
        "source_of_truth": ["document_structured_statutes", "judgment treatment extraction"],
    },
    "AMENDS_SECTION": {
        "source": "AmendmentOperation",
        "target": "Section",
        "cardinality": "0:N",
        "required_properties": ["operation_type"],
        "optional_properties": ["target_section", "target_anchor", "new_section_label", "confidence"],
        "source_of_truth": ["act_amendment_operations"],
    },
    "HAS_OPERATION": {
        "source": "Amendment",
        "target": "AmendmentOperation",
        "cardinality": "1:N",
        "required_properties": ["amendment_document_id", "sequence_no"],
        "optional_properties": ["operation_type", "confidence"],
        "source_of_truth": ["act_amendment_operations"],
    },
    "SUPERSEDES": {
        "source": ["Act", "ActVersion", "SectionVersion"],
        "target": ["Act", "ActVersion", "SectionVersion"],
        "cardinality": "0:1",
        "required_properties": ["supersedes_document_id"],
        "optional_properties": [],
        "source_of_truth": ["documents.supersedes_document_id"],
    },
    "HAS_SUBSECTION": {
        "source": "Section",
        "target": "Section",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["parent_section_number", "section_number", "confidence"],
        "source_of_truth": ["deterministic statute text parser"],
    },
    "HAS_DEFINITION": {
        "source": "Act",
        "target": ["LegalConcept", "Section"],
        "cardinality": "0:N",
        "required_properties": ["term", "definition"],
        "optional_properties": ["section_number", "source_section_id", "confidence"],
        "source_of_truth": ["deterministic statute text parser"],
    },
    "HAS_JUDGMENT": {
        "source": "Matter",
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "source_reference"],
        "source_of_truth": ["matter interactions", "authority resolution"],
    },
    "HAS_MATTER_DOCUMENT": {
        "source": "Matter",
        "target": "Document",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["category", "status"],
        "source_of_truth": ["matter_store.documents"],
    },
    "INVOLVES_PARTY": {
        "source": "Matter",
        "target": "Party",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["role"],
        "source_of_truth": ["matter_store.clientName", "matter intake"],
    },
    "HAS_PARTICIPATION": {
        "source": ["Matter", "Case", "Judgment"],
        "target": "LegalParticipation",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "source_reference"],
        "source_of_truth": ["matter intake", "document_judgment_metadata.parties_json"],
    },
    "PARTICIPANT": {
        "source": "LegalParticipation",
        "target": "Party",
        "cardinality": "1:1",
        "required_properties": [],
        "optional_properties": ["confidence"],
        "source_of_truth": ["matter parties", "document_judgment_metadata.parties_json"],
    },
    "HAS_ROLE": {
        "source": "LegalParticipation",
        "target": "LegalRole",
        "cardinality": "1:1",
        "required_properties": [],
        "optional_properties": ["confidence"],
        "source_of_truth": ["controlled vocabulary", "matter intake", "document_judgment_metadata.parties_json"],
    },
    "HAS_LEGAL_CONCEPT": {
        "source": ["Case", "Judgment", "SectionVersion", "Issue", "Holding", "Ratio"],
        "target": "LegalConcept",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "source_reference", "extraction_schema_version"],
        "source_of_truth": ["legal concept resolver", "master judgment extraction payload"],
    },
    "BROADER_CONCEPT": {
        "source": "LegalConcept",
        "target": "LegalConcept",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence"],
        "source_of_truth": ["legal_concept_links"],
    },
    "RELATED_CONCEPT": {
        "source": "LegalConcept",
        "target": "LegalConcept",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence"],
        "source_of_truth": ["legal_concept_links"],
    },
    "CONCEPT_ALIAS_OF": {
        "source": "ConceptAlias",
        "target": "LegalConcept",
        "cardinality": "1:1",
        "required_properties": [],
        "optional_properties": ["confidence", "language", "alias_type"],
        "source_of_truth": ["legal_concept_aliases"],
    },
    "APPLIES_TEST": {
        "source": ["Case", "Holding", "Ratio"],
        "target": "LegalTest",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "source_paragraph"],
        "source_of_truth": ["master judgment extraction payload", "element materializer"],
    },
    "HAS_ELEMENT": {
        "source": ["LegalTest", "LegalConcept"],
        "target": "ClaimElement",
        "cardinality": "1:N",
        "required_properties": [],
        "optional_properties": ["sequence_no", "temporal_gate"],
        "source_of_truth": ["controlled legal concept vocabulary"],
    },
    "SATISFIES_ELEMENT": {
        "source": ["Fact", "Holding"],
        "target": "ClaimElement",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "source_paragraph"],
        "source_of_truth": ["master judgment extraction payload", "element materializer"],
    },
    "FAILS_ELEMENT": {
        "source": ["Fact", "Holding"],
        "target": "ClaimElement",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "source_paragraph"],
        "source_of_truth": ["master judgment extraction payload", "element materializer"],
    },
    "HAS_BURDEN": {
        "source": ["Issue", "ClaimElement"],
        "target": "BurdenOfProof",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "party_role"],
        "source_of_truth": ["master judgment extraction payload"],
    },
    "HAS_STANDARD": {
        "source": "BurdenOfProof",
        "target": "StandardOfProof",
        "cardinality": "0:1",
        "required_properties": [],
        "optional_properties": ["confidence"],
        "source_of_truth": ["master judgment extraction payload"],
    },
    "RESULTS_IN": {
        "source": "Holding",
        "target": "LegalOutcome",
        "cardinality": "0:1",
        "required_properties": [],
        "optional_properties": ["confidence"],
        "source_of_truth": ["master judgment extraction payload"],
    },
    "HAS_AUTHORITY_STATUS": {
        "source": ["Case", "Judgment", "Ratio"],
        "target": "AuthorityStatus",
        "cardinality": "0:N",
        "required_properties": ["confidence", "ontology_version"],
        "optional_properties": ["issue_id", "legal_concept_id", "binding_weight", "persuasive_weight"],
        "source_of_truth": ["case_authority_status", "deterministic authority materializer"],
    },
    "QUESTIONED_BY": {
        "source": "Case",
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": ["quote", "source_paragraph", "confidence"],
        "optional_properties": ["scope", "issue_id", "legal_concept_id", "treatment_strength"],
        "source_of_truth": ["case_treatments", "master judgment extraction payload"],
    },
    "NOT_FOLLOWED_BY": {
        "source": "Case",
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": ["quote", "source_paragraph", "confidence"],
        "optional_properties": ["scope", "issue_id", "legal_concept_id", "treatment_strength"],
        "source_of_truth": ["case_treatments", "master judgment extraction payload"],
    },
    "DEPARTS_FROM": {
        "source": "Case",
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": ["quote", "source_paragraph", "confidence"],
        "optional_properties": ["scope", "issue_id", "legal_concept_id", "treatment_strength"],
        "source_of_truth": ["case_treatments", "master judgment extraction payload"],
    },
    "LIMITED_BY": {
        "source": "Case",
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": ["quote", "source_paragraph", "confidence"],
        "optional_properties": ["scope", "issue_id", "legal_concept_id", "limitation_reason"],
        "source_of_truth": ["case_treatments", "contradiction_signals"],
    },
    "CONFLICTS_WITH": {
        "source": ["Case", "Holding", "Ratio"],
        "target": ["Case", "Holding", "Ratio"],
        "cardinality": "0:N",
        "required_properties": ["confidence", "provenance"],
        "optional_properties": ["issue_id", "legal_concept_id", "conflict_status", "source_excerpt"],
        "source_of_truth": ["conflict detection materializer", "operator review"],
    },
    "HARMONIZED_WITH": {
        "source": "LegalConflict",
        "target": "ConflictResolution",
        "cardinality": "0:1",
        "required_properties": ["confidence", "provenance"],
        "optional_properties": ["resolution_reason"],
        "source_of_truth": ["conflict review queue", "deterministic hierarchy rules"],
    },
    "LIMITED_TO_FACTS": {
        "source": ["Case", "Ratio", "LegalConflict"],
        "target": "DistinguishingReason",
        "cardinality": "0:N",
        "required_properties": ["confidence", "source_paragraph"],
        "optional_properties": ["quote", "issue_id"],
        "source_of_truth": ["case_treatments", "contradiction_signals"],
    },
    "LIMITED_TO_ISSUE": {
        "source": ["Case", "Ratio", "LegalConflict"],
        "target": ["Issue", "DistinguishingReason"],
        "cardinality": "0:N",
        "required_properties": ["confidence", "source_paragraph"],
        "optional_properties": ["quote", "legal_concept_id"],
        "source_of_truth": ["case_treatments", "contradiction_signals"],
    },
    "DISTINGUISHED_ON_FACTS": {
        "source": "Case",
        "target": "DistinguishingReason",
        "cardinality": "0:N",
        "required_properties": ["quote", "source_paragraph", "confidence"],
        "optional_properties": ["target_case_id", "issue_id"],
        "source_of_truth": ["case_treatments", "contradiction_signals"],
    },
    "DISTINGUISHED_ON_LAW": {
        "source": "Case",
        "target": "DistinguishingReason",
        "cardinality": "0:N",
        "required_properties": ["quote", "source_paragraph", "confidence"],
        "optional_properties": ["target_case_id", "legal_concept_id"],
        "source_of_truth": ["case_treatments", "contradiction_signals"],
    },
    "RESOLVES_CONFLICT": {
        "source": "ConflictResolution",
        "target": "LegalConflict",
        "cardinality": "1:N",
        "required_properties": ["confidence", "provenance"],
        "optional_properties": ["controlling_case_id", "review_status"],
        "source_of_truth": ["conflict review queue", "deterministic hierarchy rules"],
    },
    "INTERRUPTS_LIMITATION_PERIOD": {
        "source": "InterruptionEvent",
        "target": "LegalTest",
        "cardinality": "0:N",
        "required_properties": ["interruption_type", "confidence"],
        "optional_properties": ["event_date", "legal_concept_id", "source_paragraph"],
        "source_of_truth": ["adverse possession temporal materializer"],
    },
    "HAS_EXTRACTION_PAYLOAD": {
        "source": ["Document", "Judgment"],
        "target": "ExtractionPayload",
        "cardinality": "0:1",
        "required_properties": ["extraction_schema_version", "source_text_hash"],
        "optional_properties": ["validation_status", "confidence"],
        "source_of_truth": ["master extraction cache"],
    },
    "HAS_VERBATIM_QUOTE": {
        "source": ["Ratio", "Citation", "AuthorityStatus"],
        "target": "ExtractionPayload",
        "cardinality": "0:N",
        "required_properties": ["quote", "source_paragraph"],
        "optional_properties": ["source_page", "confidence"],
        "source_of_truth": ["master judgment extraction payload"],
    },
    "PARTICIPATES_IN": {
        "source": "LegalParticipation",
        "target": ["Matter", "Case", "Judgment"],
        "cardinality": "1:1",
        "required_properties": [],
        "optional_properties": ["confidence"],
        "source_of_truth": ["matter intake", "document_judgment_metadata.parties_json"],
    },
    "HAS_PIN": {
        "source": "Document",
        "target": "PinReference",
        "cardinality": "0:N",
        "required_properties": ["document_id"],
        "optional_properties": ["page", "paragraph", "section", "chunk_index"],
        "source_of_truth": ["authority resolution pin metadata"],
    },
    "REPEALS": {
        "source": ["Act", "ActVersion", "SectionVersion"],
        "target": ["Act", "ActVersion", "SectionVersion"],
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "evidence"],
        "source_of_truth": ["act_amendment_operations", "documents.metadata_json"],
    },
    "REPEALED_BY": {
        "source": ["Act", "ActVersion", "SectionVersion"],
        "target": ["Act", "ActVersion", "SectionVersion"],
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "evidence"],
        "source_of_truth": ["act_amendment_operations", "documents.metadata_json"],
    },
    "AMENDED_BY": {
        "source": ["Act", "ActVersion", "SectionVersion"],
        "target": ["Amendment", "ActVersion", "SectionVersion"],
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "evidence", "inferred"],
        "source_of_truth": ["inverse of AMENDS", "act_amendment_operations", "documents.metadata_json"],
    },
    "INTERPRETED_BY": {
        "source": "SectionVersion",
        "target": "Case",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "evidence", "inferred"],
        "source_of_truth": ["inverse of INTERPRETS_SECTION"],
    },
    "SECTION_OF": {
        "source": "Section",
        "target": "Act",
        "cardinality": "1:1",
        "required_properties": [],
        "optional_properties": ["confidence", "inferred"],
        "source_of_truth": ["inverse of HAS_SECTION"],
    },
    "VERSION_OF": {
        "source": ["ActVersion", "SectionVersion"],
        "target": ["Act", "Section"],
        "cardinality": "1:1",
        "required_properties": [],
        "optional_properties": ["confidence", "inferred"],
        "source_of_truth": ["inverse of HAS_VERSION", "canonical_act_versions", "canonical_section_versions"],
    },
    "COMMENCES": {
        "source": ["Document", "Amendment"],
        "target": "ActVersion",
        "cardinality": "0:N",
        "required_properties": [],
        "optional_properties": ["confidence", "evidence", "gazette_notice"],
        "source_of_truth": ["documents.metadata_json"],
    },
    "HAS_SECTION": {
        "source": "Act",
        "target": "Section",
        "cardinality": "0:N",
        "required_properties": ["label"],
        "optional_properties": ["section_kind", "part_label", "sub_part_label"],
        "source_of_truth": ["document_paragraphs", "document_chunks", "act_consolidations"],
    },
    "HAS_REGULATION": {
        "source": "Act",
        "target": "Regulation",
        "cardinality": "0:N",
        "required_properties": ["label"],
        "optional_properties": ["section_kind"],
        "source_of_truth": ["document_paragraphs", "document_chunks"],
    },
    "HAS_SCHEDULE": {
        "source": "Act",
        "target": "Schedule",
        "cardinality": "0:N",
        "required_properties": ["label"],
        "optional_properties": ["contains_table_like"],
        "source_of_truth": ["document_paragraphs", "document_chunks", "act_consolidations"],
    },
    "HAS_TEMPORAL_MARKER": {
        "source": "Document",
        "target": "TemporalMarker",
        "cardinality": "0:N",
        "required_properties": ["date_type", "date_value"],
        "optional_properties": ["source_field"],
        "source_of_truth": [
            "documents.publication_date",
            "documents.metadata_json",
            "document_judgment_metadata.true_judgment_date",
        ],
    },
}

SOURCE_OF_TRUTH_RULES: list[dict[str, Any]] = [
    {
        "name": "Documents are canonical graph roots",
        "rule": "A graph node backed by a crawled legal document must resolve to documents.id before any derived node is trusted.",
    },
    {
        "name": "Judgment structure wins over loose entities",
        "rule": "For judges, parties, issues, holdings, and orders, document_judgment_metadata overrides document_entities when both exist.",
    },
    {
        "name": "Structured statute references win over raw citation strings",
        "rule": "When a statute appears in both document_structured_statutes and document_citation_links, the structured statute record is authoritative for act_name, section_ref, and canonical_statute_id.",
    },
    {
        "name": "Amendment operations are primary for legislative changes",
        "rule": "act_amendment_operations is the authoritative source for section-level amendment behavior; document metadata is only fallback evidence.",
    },
    {
        "name": "Doctrinal nodes must point back to judgment structure",
        "rule": "Facts, ratio, obiter, and deontic nodes are trusted only when they are derived from persisted judgment structure fields rather than transient model output.",
    },
    {
        "name": "Canonical identifiers must be stable",
        "rule": "canonical_citation and canonical_statute_id are immutable identifiers once published, unless corrected by reviewed migration.",
    },
    {
        "name": "Internal links outrank unresolved placeholders",
        "rule": "If an authority resolves to an internal document node, use linked_document_id and retain raw citation text only as evidence metadata.",
    },
]

RELATIONSHIP_CONSTRAINTS: list[dict[str, Any]] = [
    {
        "relationship": "CITES_CASE",
        "constraint": "linked_document_id may equal the target case document, but must never equal the source judgment document.",
    },
    {
        "relationship": "CITES_STATUTE",
        "constraint": "A statute edge should carry either canonical_statute_id or act_name; internal statute edges should also carry linked_document_id when resolvable.",
    },
    {
        "relationship": "AMENDS",
        "constraint": "An amendment must not target itself and should resolve to at least one principal Act or enter the amendment review queue.",
    },
    {
        "relationship": "HAS_OPERATION",
        "constraint": "sequence_no must be unique per amendment document.",
    },
    {
        "relationship": "SUPERSEDES",
        "constraint": "supersedes_document_id must not self-link and supersession chains must remain acyclic.",
    },
    {
        "relationship": "RESOLVES_ISSUE",
        "constraint": "A holding may resolve only an issue that belongs to the same judgment root and is identified by issue_index.",
    },
    {
        "relationship": "HAS_TEMPORAL_MARKER",
        "constraint": "Temporal markers should deduplicate identical date_type/date_value pairs per root document and preserve the underlying source field.",
    },
]


def get_wakili_legal_graph_ontology() -> dict[str, Any]:
    return {
        "version": ONTOLOGY_VERSION,
        "description": "Authoritative ontology for the Wakili legal knowledge graph across judgments, Acts, amendments, subsidiary legislation, and legal authorities.",
        "node_types": deepcopy(NODE_TYPES),
        "relationship_types": deepcopy(RELATIONSHIP_TYPES),
        "source_of_truth_rules": deepcopy(SOURCE_OF_TRUTH_RULES),
        "relationship_constraints": deepcopy(RELATIONSHIP_CONSTRAINTS),
    }


def validate_node_type(node_type: str) -> bool:
    return str(node_type or "").strip() in NODE_TYPES


def _parse_iso_date(value: object) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    return raw[:10] if len(raw) >= 10 else None


def _date_in_range(point: str, start: str | None, end: str | None) -> bool:
    if start and point < start:
        return False
    if end and point > end:
        return False
    return True


def _court_rank(level: str | None) -> int:
    normalized = str(level or "").strip().lower()
    ranks = {
        "primary_court": 1,
        "district_court": 2,
        "resident_magistrate": 3,
        "high_court": 4,
        "court_of_appeal": 5,
        "coa": 5,
    }
    return ranks.get(normalized, 0)


def _is_coa_level(level: object) -> bool:
    return str(level or "").strip().lower() in {"court_of_appeal", "coa"}


def _panel_size(value: object) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _smaller_coa_panel(source: dict[str, Any], target: dict[str, Any]) -> bool:
    if not (_is_coa_level(source.get("court_level")) and _is_coa_level(target.get("court_level"))):
        return False
    source_panel = _panel_size(source.get("panel_size"))
    target_panel = _panel_size(target.get("panel_size"))
    return source_panel is not None and target_panel is not None and source_panel < target_panel


def validate_node(node_type: str, properties: dict[str, Any] | None) -> tuple[bool, str | None]:
    normalized_type = str(node_type or "").strip()
    schema = NODE_TYPES.get(normalized_type)
    if schema is None:
        return False, f"Unknown node type: {normalized_type}"
    payload = dict(properties or {})
    for field_name in schema.get("required_properties") or []:
        value = payload.get(field_name)
        if value is None or (isinstance(value, str) and not value.strip()):
            return False, f"Missing required {normalized_type} field: {field_name}"
    if normalized_type in {"Case", "Judgment"}:
        language = str(payload.get("language") or "").strip().upper()
        if language and language not in {"EN", "SW", "MIXED"}:
            return False, "language must be one of EN|SW|MIXED"
    if normalized_type in JURISDICTION_REQUIRED_NODE_TYPES:
        jurisdiction = str(payload.get("jurisdiction") or "").strip().lower()
        if jurisdiction not in TANZANIA_JURISDICTIONS:
            return False, f"{normalized_type}.jurisdiction must be mainland, zanzibar, or union"
    if normalized_type in {"ActVersion", "SectionVersion"}:
        start = _parse_iso_date(payload.get("valid_from"))
        end = _parse_iso_date(payload.get("valid_to"))
        if not start:
            return False, f"{normalized_type}.valid_from is required"
        if end and end < start:
            return False, f"{normalized_type}.valid_to cannot be earlier than valid_from"
    return True, None


def validate_edge(
    source_type: str,
    edge_type: str,
    target_type: str,
    *,
    source_id: str | None = None,
    target_id: str | None = None,
    source_properties: dict[str, Any] | None = None,
    target_properties: dict[str, Any] | None = None,
    edge_properties: dict[str, Any] | None = None,
) -> tuple[bool, str | None]:
    normalized_edge = str(edge_type or "").strip()
    relation = RELATIONSHIP_TYPES.get(normalized_edge)
    if relation is None:
        return False, f"Unknown edge type: {normalized_edge}"

    normalized_source_type = str(source_type or "").strip()
    normalized_target_type = str(target_type or "").strip()
    allowed_sources = relation.get("source")
    allowed_targets = relation.get("target")
    source_ok = normalized_source_type in allowed_sources if isinstance(allowed_sources, list) else allowed_sources == normalized_source_type
    target_ok = normalized_target_type in allowed_targets if isinstance(allowed_targets, list) else allowed_targets == normalized_target_type
    if not source_ok or not target_ok:
        return False, (
            f"Illegal edge pairing for {normalized_edge}: "
            f"{normalized_source_type} -> {normalized_target_type}"
        )

    source_key = str(source_id or "").strip()
    target_key = str(target_id or "").strip()
    if source_key and target_key and source_key == target_key and normalized_edge in {"CITES_CASE", "AMENDS", "SUPERSEDES", "REPEALS", "REPEALED_BY"}:
        return False, f"Self edge is forbidden for {normalized_edge}"

    props = dict(edge_properties or {})
    if normalized_edge == "OVERRULES" and not str(props.get("overruling_reason") or "").strip():
        return False, "OVERRULES requires overruling_reason"
    if normalized_edge == "DISTINGUISHES" and not str(props.get("distinguishing_reason") or "").strip():
        return False, "DISTINGUISHES requires distinguishing_reason"
    if normalized_edge == "DISTINGUISHES":
        distinction_type = str(props.get("distinction_type") or "factual").strip().lower()
        allowed_distinction_types = {"factual", "procedural", "legal_principle"}
        if distinction_type not in allowed_distinction_types:
            return False, "DISTINGUISHES distinction_type must be factual, procedural, or legal_principle"
    if normalized_edge == "INTERPRETS_SECTION":
        if normalized_target_type != "SectionVersion":
            return False, "INTERPRETS_SECTION must target SectionVersion"
        if not str(props.get("interpretation_type") or "").strip():
            return False, "INTERPRETS_SECTION requires interpretation_type"
        src = dict(source_properties or {})
        tgt = dict(target_properties or {})
        decision_date = _parse_iso_date(src.get("decision_date") or src.get("judgment_date"))
        if not decision_date:
            decision_date = _parse_iso_date(props.get("decision_date") or props.get("judgment_date"))
        if not decision_date:
            return False, "INTERPRETS_SECTION requires decision_date for point-in-time statute reasoning"
        valid_from = _parse_iso_date(tgt.get("valid_from"))
        valid_to = _parse_iso_date(tgt.get("valid_to"))
        if decision_date and valid_from and not _date_in_range(decision_date, valid_from, valid_to):
            return False, "Temporal statute violation: case decision date outside section validity range"
    if normalized_edge in {"OVERRULES", "REVERSES_ON_APPEAL", "FOLLOWS", "DISTINGUISHES"}:
        src = dict(source_properties or {})
        tgt = dict(target_properties or {})
        src_date = _parse_iso_date(src.get("decision_date") or src.get("judgment_date"))
        tgt_date = _parse_iso_date(tgt.get("decision_date") or tgt.get("judgment_date"))
        if src_date and tgt_date and src_date < tgt_date:
            return False, "Chronology violation: treatment source predates target"
        if normalized_edge in {"OVERRULES", "REVERSES_ON_APPEAL"}:
            src_rank = _court_rank(src.get("court_level"))
            tgt_rank = _court_rank(tgt.get("court_level"))
            if src_rank and tgt_rank and src_rank < tgt_rank:
                action = "overrule" if normalized_edge == "OVERRULES" else "reverse on appeal from"
                return False, f"Hierarchy violation: lower court cannot {action} higher court"
            if _smaller_coa_panel(src, tgt):
                action = "overrule" if normalized_edge == "OVERRULES" else "reverse on appeal from"
                return False, f"Panel precedence violation: smaller CoA panel cannot {action} larger panel"
        if normalized_edge == "DISTINGUISHES":
            distinction_type = str(props.get("distinction_type") or "factual").strip().lower()
            if distinction_type == "legal_principle" and _smaller_coa_panel(src, tgt):
                return False, "Panel precedence violation: smaller CoA panel cannot distinguish a larger panel on legal principle"

    return True, None
