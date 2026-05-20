from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from itertools import combinations
from typing import Any

_GENERIC_CONCEPTS = {
    "appeal",
    "appeals",
    "application",
    "applications",
    "civil law",
    "civil procedure",
    "commercial law",
    "criminal procedure",
    "criminal law",
    "court",
    "courts",
    "evidence",
    "facts",
    "issue",
    "issues",
    "judgment",
    "jurisdiction",
    "law",
    "land law",
    "legal procedure",
    "labour law",
    "procedure",
    "review",
    "sentence",
    "sentencing",
    "trial",
}

_APPELLATE_NOISE_PATTERNS = (
    "evaluate the evidence",
    "evaluation of the evidence",
    "re-evaluate the evidence",
    "weight of evidence",
    "misdirection on facts",
    "misdirected itself on facts",
    "failed to consider the evidence",
    "failed to evaluate the evidence",
    "whether the appeal has merit",
    "whether the appeal had merit",
    "whether the trial court erred",
    "whether the high court erred",
    "whether the magistrate erred",
    "whether the lower court erred",
    "whether the sentence was excessive",
    "severity of sentence",
    "extension of time",
    "extend time",
    "leave to appeal",
    "granted leave to appeal",
    "sought leave to appeal",
    "file appeal out of time",
    "file an appeal out of time",
    "impugned decision",
    "grounds of appeal",
)

_CONTRADICTION_TEST_ALLOWLIST = {
    "adverse_possession_mainland",
    "criminal_identification_evidence",
    "winding_up_just_and_equitable",
}

_CONTRADICTION_CONCEPT_ALLOWLIST = {
    "adverse possession",
    "identification evidence",
    "winding up",
    "judicial review",
    "bail",
}


def _safe_json_list(raw_value: object) -> list[dict[str, Any]]:
    if isinstance(raw_value, list):
        return [dict(item) for item in raw_value if isinstance(item, dict)]
    if not isinstance(raw_value, str) or not raw_value.strip():
        return []
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return []
    return [dict(item) for item in parsed if isinstance(item, dict)] if isinstance(parsed, list) else []


def _safe_json_dict(raw_value: object) -> dict[str, Any]:
    if isinstance(raw_value, dict):
        return dict(raw_value)
    if not isinstance(raw_value, str) or not raw_value.strip():
        return {}
    try:
        parsed = json.loads(raw_value)
    except json.JSONDecodeError:
        return {}
    return dict(parsed) if isinstance(parsed, dict) else {}


def _normalize(text: object) -> str:
    return " ".join(str(text or "").strip().lower().split())


def _token_set(text: object) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", _normalize(text))
        if len(token) > 2
    }


def _issue_similarity(left: str, right: str) -> float:
    left_tokens = _token_set(left)
    right_tokens = _token_set(right)
    if not left_tokens or not right_tokens:
        return 0.0
    overlap = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return overlap / union if union else 0.0


def _normalized_concept_label(value: object) -> str:
    return re.sub(r"[_\s]+", " ", str(value or "").strip().lower()).strip()


def _specific_concepts(values: set[str] | list[str] | tuple[str, ...]) -> set[str]:
    output: set[str] = set()
    for value in values:
        rendered = str(value or "").strip()
        normalized = _normalized_concept_label(rendered)
        if not normalized or normalized in _GENERIC_CONCEPTS:
            continue
        if normalized.endswith(" appeal") or normalized.endswith(" jurisdiction"):
            continue
        output.add(rendered)
    return output


def _shared_specific_concepts(left: set[str], right: set[str]) -> list[str]:
    left_map = {_normalized_concept_label(value): str(value).strip() for value in _specific_concepts(left)}
    right_map = {_normalized_concept_label(value): str(value).strip() for value in _specific_concepts(right)}
    shared_keys = sorted(set(left_map) & set(right_map))
    return [left_map[key] or right_map[key] for key in shared_keys]


def _shared_seeded_concepts(left: set[str], right: set[str]) -> list[str]:
    allowed = {_normalized_concept_label(value) for value in _CONTRADICTION_CONCEPT_ALLOWLIST}
    return [
        value
        for value in _shared_specific_concepts(left, right)
        if _normalized_concept_label(value) in allowed
    ]


def _shared_seeded_tests(left: set[str], right: set[str]) -> list[str]:
    shared = sorted(set(str(value).strip() for value in left) & set(str(value).strip() for value in right))
    return [value for value in shared if value in _CONTRADICTION_TEST_ALLOWLIST]


def _is_appellate_noise_issue(text: object) -> bool:
    normalized = _normalize(text)
    if not normalized:
        return True
    if any(pattern in normalized for pattern in _APPELLATE_NOISE_PATTERNS):
        return True
    tokens = _token_set(normalized)
    if not tokens:
        return True
    generic_tokens = {
        "appeal",
        "court",
        "evidence",
        "facts",
        "judge",
        "judgment",
        "merit",
        "sentence",
        "trial",
        "whether",
        "erred",
        "error",
        "wrong",
    }
    non_generic_tokens = {token for token in tokens if token not in generic_tokens}
    return len(non_generic_tokens) <= 2


def _looks_like_caption_issue(text: object) -> bool:
    raw = str(text or "").strip()
    if not raw:
        return True
    lowered = raw.lower()
    if len(raw) < 24:
        return True
    if any(marker in lowered for marker in ("in the high court", "in the court of appeal", "coram:", "criminal application no", "misc.", "land case no", "civil appeal no")):
        return True
    alpha = re.sub(r"[^A-Za-z]+", "", raw)
    if alpha:
        uppercase_ratio = sum(1 for char in alpha if char.isupper()) / max(1, len(alpha))
        if uppercase_ratio > 0.7:
            return True
    return False


def _outcomes_comparable(left: str, right: str) -> bool:
    pair = {str(left or "").strip().lower(), str(right or "").strip().lower()}
    return pair in ({"allowed", "dismissed"}, {"convicted", "acquitted"})


def _proceeding_family(title: object) -> str:
    lowered = _normalize(title)
    if "criminal" in lowered or "republic" in lowered:
        return "criminal"
    if "land" in lowered or "occupancy" in lowered or "village land" in lowered:
        return "land"
    if "labour" in lowered or "labor" in lowered:
        return "labour"
    if "commercial" in lowered:
        return "commercial"
    if "civil" in lowered:
        return "civil"
    if "misc." in lowered or "miscellaneous" in lowered:
        return "miscellaneous"
    return "unknown"


def _outcome_bucket(*texts: object) -> str:
    merged = " ".join(str(text or "").lower() for text in texts)
    if any(term in merged for term in ("appeal_allowed", "application_granted", "petition_allowed", "claim_allowed")):
        return "allowed"
    if any(term in merged for term in ("appeal_dismissed", "application_dismissed", "petition_dismissed", "claim_dismissed")):
        return "dismissed"
    if any(term in merged for term in ("conviction_upheld", "convicted")):
        return "convicted"
    if any(term in merged for term in ("acquitted", "acquittal", "conviction_quashed")):
        return "acquitted"
    if any(term in merged for term in ("appeal is allowed", "application is granted", "petition succeeds", "claim succeeds", "allowed with costs", "granted")):
        return "allowed"
    if any(term in merged for term in ("appeal is dismissed", "application is dismissed", "petition is dismissed", "claim is dismissed", "dismissed with costs", "denied", "fails")):
        return "dismissed"
    if "convicted" in merged:
        return "convicted"
    if "acquitted" in merged or "acquit" in merged:
        return "acquitted"
    return "unknown"


def _court_rank(level: object) -> int:
    raw = _normalize(level)
    if "court_of_appeal" in raw or "court of appeal" in raw or "tzca" in raw:
        return 4
    if "high_court" in raw or "high court" in raw or "tzhc" in raw:
        return 3
    if "district" in raw:
        return 2
    if "primary" in raw:
        return 1
    return 0


def _stable_id(prefix: str, *parts: object) -> str:
    payload = "|".join(str(part or "") for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}:{digest}"


@dataclass(frozen=True)
class ConflictCandidate:
    source_case_id: str
    target_case_id: str
    issue_text: str
    shared_tests: list[str]
    shared_concepts: list[str]
    issue_overlap_score: float
    source_outcome: str
    target_outcome: str
    source_excerpt: str
    target_excerpt: str
    source_court_level: str
    target_court_level: str
    confidence: float
    controlling_case_id: str | None


@dataclass(frozen=True)
class DistinguishingCandidate:
    source_case_id: str
    target_case_id: str
    reason_id: str
    edge_type: str
    reason_type: str
    text: str
    quote: str
    source_paragraph: str
    confidence: float


def extract_case_profile(row: dict[str, Any]) -> dict[str, Any]:
    metadata = _safe_json_dict(row.get("metadata_json"))
    payload = _safe_json_dict(metadata.get("master_extraction_payload"))
    issues = _safe_json_list(row.get("issues_framed_json"))
    holdings = _safe_json_list(row.get("holdings_json"))
    contradiction_signals = _safe_json_list(payload.get("contradiction_signals"))
    case_treatments = _safe_json_list(payload.get("case_treatments"))
    structured_outcomes = _safe_json_list(payload.get("structured_outcomes"))

    primary_issue = ""
    for issue in issues:
        primary_issue = str(issue.get("issue_text") or issue.get("text") or "").strip()
        if primary_issue:
            break

    holding_text = ""
    for holding in holdings:
        holding_text = str(holding.get("holding_text") or holding.get("text") or "").strip()
        if holding_text:
            break

    outcome_text = " ".join(
        [
            str(row.get("outcome_type") or ""),
            str(row.get("primary_order_text") or ""),
            holding_text,
            " ".join(str(item.get("primary_order_text") or item.get("outcome_type") or "") for item in structured_outcomes),
        ]
    ).strip()

    concepts: set[str] = set()
    for issue in issues:
        for concept in issue.get("legal_concepts") or []:
            normalized = str(concept or "").strip()
            if normalized:
                concepts.add(normalized)

    return {
        "document_id": str(row.get("document_id") or row.get("id") or "").strip(),
        "case_id": f"Case:{str(row.get('document_id') or row.get('id') or '').strip()}",
        "title": str(row.get("title") or "").strip(),
        "citation": str(row.get("citation") or "").strip(),
        "court_level": str(row.get("normalized_court_level") or row.get("court") or "").strip(),
        "jurisdiction": str(row.get("jurisdiction") or "").strip(),
        "proceeding_family": _proceeding_family(row.get("title")),
        "decision_date": str(row.get("true_judgment_date") or "").strip(),
        "year": int(row.get("year") or 0),
        "issue_text": primary_issue,
        "issue_tokens": _token_set(primary_issue),
        "holding_text": holding_text,
        "outcome": _outcome_bucket(outcome_text),
        "concepts": _specific_concepts(concepts),
        "issue_concepts": concepts,
        "tests": set(),
        "contradiction_signals": contradiction_signals,
        "case_treatments": case_treatments,
    }


def build_distinguishing_candidates(profiles: list[dict[str, Any]]) -> list[DistinguishingCandidate]:
    citation_map = {
        str(profile.get("citation") or "").strip().lower(): profile
        for profile in profiles
        if str(profile.get("citation") or "").strip()
    }
    candidates: list[DistinguishingCandidate] = []
    seen: set[str] = set()
    for profile in profiles:
        for treatment in profile.get("case_treatments") or []:
            if str(treatment.get("treatment_type") or "").strip().lower() != "distinguishes":
                continue
            target = citation_map.get(str(treatment.get("cited_case_reference") or "").strip().lower())
            if target is None:
                continue
            quote = str(treatment.get("quote") or "").strip()
            source_paragraph = str(treatment.get("source_paragraph") or "").strip() or "review_required"
            lowered = quote.lower()
            reason_type = "legal_principle" if any(term in lowered for term in ("principle", "law", "statute", "section")) else "factual"
            edge_type = "DISTINGUISHED_ON_LAW" if reason_type == "legal_principle" else "DISTINGUISHED_ON_FACTS"
            reason_id = _stable_id(
                "DistinguishingReason",
                profile["document_id"],
                target["document_id"],
                reason_type,
                source_paragraph,
            )
            dedupe_key = f"{profile['document_id']}|{target['document_id']}|{reason_type}|{source_paragraph}"
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            candidates.append(
                DistinguishingCandidate(
                    source_case_id=str(profile["case_id"]),
                    target_case_id=str(target["case_id"]),
                    reason_id=reason_id,
                    edge_type=edge_type,
                    reason_type=reason_type,
                    text=quote[:400] or "Potential distinguishing reason extracted from treatment context.",
                    quote=quote[:1200],
                    source_paragraph=source_paragraph,
                    confidence=max(0.55, min(0.9, float(treatment.get("confidence") or 0.66))),
                )
            )
    return candidates


def detect_conflict_candidates(profiles: list[dict[str, Any]]) -> list[ConflictCandidate]:
    distinguished_pairs = {
        (candidate.source_case_id, candidate.target_case_id)
        for candidate in build_distinguishing_candidates(profiles)
    }
    candidates: list[ConflictCandidate] = []
    for left, right in combinations(profiles, 2):
        if left["outcome"] == "unknown" or right["outcome"] == "unknown" or left["outcome"] == right["outcome"]:
            continue
        if not _outcomes_comparable(left["outcome"], right["outcome"]):
            continue
        if left["proceeding_family"] != "unknown" and right["proceeding_family"] != "unknown" and left["proceeding_family"] != right["proceeding_family"]:
            continue
        if left["jurisdiction"] and right["jurisdiction"] and left["jurisdiction"] != right["jurisdiction"]:
            continue
        shared_tests = _shared_seeded_tests(
            set(left.get("tests") or set()),
            set(right.get("tests") or set()),
        )
        shared_concepts = _shared_seeded_concepts(
            set(left.get("concepts") or set()),
            set(right.get("concepts") or set()),
        )
        if not shared_tests and not shared_concepts:
            continue
        left_issue_noise = _looks_like_caption_issue(left["issue_text"]) or _is_appellate_noise_issue(left["issue_text"])
        right_issue_noise = _looks_like_caption_issue(right["issue_text"]) or _is_appellate_noise_issue(right["issue_text"])
        issue_similarity = 0.0
        if not left_issue_noise and not right_issue_noise:
            issue_similarity = _issue_similarity(left["issue_text"], right["issue_text"])
        if (left["case_id"], right["case_id"]) in distinguished_pairs or (right["case_id"], left["case_id"]) in distinguished_pairs:
            continue

        left_rank = _court_rank(left["court_level"])
        right_rank = _court_rank(right["court_level"])
        controlling_case_id: str | None = None
        if left_rank != right_rank:
            controlling_case_id = left["case_id"] if left_rank > right_rank else right["case_id"]
        elif int(left.get("year") or 0) != int(right.get("year") or 0):
            controlling_case_id = left["case_id"] if int(left.get("year") or 0) > int(right.get("year") or 0) else right["case_id"]

        issue_text = ""
        if not left_issue_noise and str(left["issue_text"] or "").strip():
            issue_text = str(left["issue_text"]).strip()
        elif not right_issue_noise and str(right["issue_text"] or "").strip():
            issue_text = str(right["issue_text"]).strip()
        else:
            issue_text = f"Conflicting treatment of {(shared_tests[0] if shared_tests else shared_concepts[0])}"

        test_score = min(0.18, 0.08 * len(shared_tests))
        concept_score = min(0.10, 0.04 * len(shared_concepts))
        issue_score = 0.08 if issue_similarity >= 0.34 else 0.0
        confidence = round(min(0.94, 0.56 + test_score + concept_score + issue_score), 4)

        candidates.append(
            ConflictCandidate(
                source_case_id=str(left["case_id"]),
                target_case_id=str(right["case_id"]),
                issue_text=issue_text,
                shared_tests=shared_tests[:3],
                shared_concepts=shared_concepts[:4],
                issue_overlap_score=round(issue_similarity, 4),
                source_outcome=str(left["outcome"]),
                target_outcome=str(right["outcome"]),
                source_excerpt=str(left["holding_text"] or left["issue_text"] or "").strip(),
                target_excerpt=str(right["holding_text"] or right["issue_text"] or "").strip(),
                source_court_level=str(left["court_level"]),
                target_court_level=str(right["court_level"]),
                confidence=confidence,
                controlling_case_id=controlling_case_id,
            )
        )
    return candidates
