# /** file legal_concepts.py shared legal concept ontology for corpus planning and graph retrieval [notes: keeps domain-wide legal query routing explicit and reviewable] */
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable


_NON_WORD_PATTERN = re.compile(r"[^a-z0-9]+")


def normalize_concept_key(value: str) -> str:
    normalized = _NON_WORD_PATTERN.sub("_", str(value or "").strip().lower()).strip("_")
    return re.sub(r"_+", "_", normalized)


@dataclass(frozen=True)
class LegalConceptSeed:
    canonical_key: str
    pref_label_en: str
    doctrine_area: str
    jurisdiction_scope: str = "union"
    pref_label_sw: str | None = None
    definition: str | None = None
    source_authority: str | None = None
    aliases: tuple[str, ...] = field(default_factory=tuple)
    broader: tuple[str, ...] = field(default_factory=tuple)
    related: tuple[str, ...] = field(default_factory=tuple)

    @property
    def concept_id(self) -> str:
        return f"LegalConcept:{self.canonical_key}"


LEGAL_CONCEPT_SEEDS: tuple[LegalConceptSeed, ...] = (
    LegalConceptSeed(
        canonical_key="land_law",
        pref_label_en="Land law",
        pref_label_sw="Sheria ya ardhi",
        doctrine_area="Land Law",
        jurisdiction_scope="union",
        definition="Doctrines and statutory regimes governing interests in land.",
        aliases=("land", "land dispute", "land ownership", "ardhi"),
    ),
    LegalConceptSeed(
        canonical_key="customary_law",
        pref_label_en="Customary law",
        pref_label_sw="Sheria ya kimila",
        doctrine_area="Customary Law",
        jurisdiction_scope="union",
        definition="Customary legal norms recognized by Tanzanian law where applicable.",
        aliases=("customary", "customary law", "sheria ya kimila", "kimila"),
        broader=("land_law",),
    ),
    LegalConceptSeed(
        canonical_key="customary_tenure",
        pref_label_en="Customary tenure",
        pref_label_sw="Umiliki wa kimila",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        definition="Customary landholding or occupancy interests.",
        aliases=("customary tenure", "customary right", "customary occupancy", "umiliki wa kimila"),
        broader=("customary_law", "land_law"),
    ),
    LegalConceptSeed(
        canonical_key="customary_right_of_occupancy",
        pref_label_en="Customary right of occupancy",
        pref_label_sw="Haki ya kumiliki ardhi kimila",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        definition="A right of occupancy grounded in customary tenure.",
        aliases=("customary right of occupancy", "cro", "haki ya kumiliki ardhi kimila"),
        broader=("customary_tenure",),
    ),
    LegalConceptSeed(
        canonical_key="granted_right_of_occupancy",
        pref_label_en="Granted right of occupancy",
        pref_label_sw="Haki ya kumiliki ardhi iliyoidhinishwa",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        definition="A formal granted right of occupancy under Tanzanian land law.",
        aliases=("granted right of occupancy", "gro", "right of occupancy"),
        broader=("land_law",),
    ),
    LegalConceptSeed(
        canonical_key="village_land",
        pref_label_en="Village land",
        pref_label_sw="Ardhi ya kijiji",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        definition="Land governed through village land legal regimes.",
        aliases=("village land", "ardhi ya kijiji"),
        broader=("land_law", "customary_tenure"),
    ),
    LegalConceptSeed(
        canonical_key="adverse_possession",
        pref_label_en="Adverse possession",
        pref_label_sw="Umiliki kwa ukaliaji bila kibali",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        definition="Acquisition or defence of land rights through continuous possession for the required limitation period.",
        aliases=(
            "adverse possession",
            "prescriptive acquisition",
            "limitation possession",
            "possession for twelve years",
            "ukaliaji bila kibali",
        ),
        broader=("land_law",),
        related=("limitation_period", "continuous_possession", "exclusive_possession"),
    ),
    LegalConceptSeed(
        canonical_key="limitation_period",
        pref_label_en="Limitation period",
        pref_label_sw="Kipindi cha ukomo wa madai",
        doctrine_area="Civil Procedure",
        jurisdiction_scope="mainland",
        definition="A statutory time period limiting when legal proceedings may be brought.",
        aliases=("limitation", "limitation period", "time bar", "twelve years", "12 years"),
        related=("adverse_possession",),
    ),
    LegalConceptSeed(
        canonical_key="criminal_evidence",
        pref_label_en="Criminal evidence",
        pref_label_sw="Ushahidi katika jinai",
        doctrine_area="Criminal Procedure",
        jurisdiction_scope="union",
        definition="Rules and principles governing proof and admissibility in criminal proceedings.",
        aliases=("criminal evidence", "evidence in criminal trial", "criminal trial evidence"),
    ),
    LegalConceptSeed(
        canonical_key="identification_evidence",
        pref_label_en="Identification evidence",
        pref_label_sw="Ushahidi wa utambuzi",
        doctrine_area="Criminal Procedure",
        jurisdiction_scope="union",
        definition="Evidence identifying an accused person or relevant actor in criminal proceedings.",
        aliases=("identification evidence", "identity evidence", "identification testimony"),
        broader=("criminal_evidence",),
    ),
    LegalConceptSeed(
        canonical_key="visual_identification",
        pref_label_en="Visual identification",
        pref_label_sw="Utambuzi wa kuona",
        doctrine_area="Criminal Procedure",
        jurisdiction_scope="union",
        definition="Identification evidence based on visual observation, including witness recognition or dock identification issues.",
        aliases=("visual identification", "visual identification evidence", "witness identification", "recognition evidence"),
        broader=("identification_evidence", "criminal_evidence"),
    ),
    LegalConceptSeed(
        canonical_key="open_possession",
        pref_label_en="Open possession",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        aliases=("open possession", "notorious possession", "visible occupation"),
        broader=("adverse_possession",),
    ),
    LegalConceptSeed(
        canonical_key="continuous_possession",
        pref_label_en="Continuous possession",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        aliases=("continuous possession", "uninterrupted possession", "continuous occupation"),
        broader=("adverse_possession",),
    ),
    LegalConceptSeed(
        canonical_key="exclusive_possession",
        pref_label_en="Exclusive possession",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        aliases=("exclusive possession", "exclusive occupation"),
        broader=("adverse_possession",),
    ),
    LegalConceptSeed(
        canonical_key="possession_without_permission",
        pref_label_en="Possession without permission",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        aliases=("without permission", "without consent", "hostile possession", "adverse occupation"),
        broader=("adverse_possession",),
    ),
    LegalConceptSeed(
        canonical_key="interruption_of_possession",
        pref_label_en="Interruption of possession",
        doctrine_area="Land Law",
        jurisdiction_scope="mainland",
        aliases=("interruption", "acknowledgment of title", "suit filed", "dispossession"),
        related=("adverse_possession", "limitation_period"),
    ),
)


def iter_legal_concept_seeds() -> Iterable[LegalConceptSeed]:
    return LEGAL_CONCEPT_SEEDS


def resolve_concept_alias(value: str) -> tuple[LegalConceptSeed, float] | None:
    normalized = normalize_concept_key(value)
    if not normalized:
        return None

    for seed in LEGAL_CONCEPT_SEEDS:
        if normalized == seed.canonical_key or normalized == normalize_concept_key(seed.pref_label_en):
            return seed, 1.0
        for alias in seed.aliases:
            if normalized == normalize_concept_key(alias):
                return seed, 0.96

    for seed in LEGAL_CONCEPT_SEEDS:
        candidates = [seed.pref_label_en, *seed.aliases]
        if any(normalized in normalize_concept_key(candidate) for candidate in candidates):
            return seed, 0.72
    return None
