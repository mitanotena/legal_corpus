from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Literal

ReasoningFramework = Literal["IRAC", "CREAC"]
BrainChannel = Literal["chat", "voice"]
VerificationStatus = Literal["verified", "mixed", "unverified"]
BurdenCertainty = Literal["GRAPH_EVIDENCED", "JURISDICTIONAL_DEFAULT", "STATUTORY_IMPLICIT", "UNKNOWN"]
LimitationStatus = Literal["BARRED", "AT_RISK", "SAFE", "CANNOT_CONFIRM"]


@dataclass(slots=True)
class BrainRiskFlag:
    type: str
    severity: Literal["low", "medium", "high"]
    message: str
    mitigation: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BrainIssue:
    issue: str
    ruleSummary: str
    applicationSummary: str
    provisionalConclusion: str
    authorityRefs: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BrainModelUsage:
    requestedMode: str
    selectedModel: str
    fallbackModel: str | None = None
    latencyMs: int = 0
    timedOut: bool = False
    partialResult: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VerificationSummary:
    confidenceScore: float
    verificationStatus: VerificationStatus
    verifiedAuthorities: list[str] = field(default_factory=list)
    suppressedAuthorities: list[str] = field(default_factory=list)
    unverifiedPropositions: list[str] = field(default_factory=list)
    deadLawRewrites: list[str] = field(default_factory=list)
    disclaimerEscalated: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BurdenCertaintySummary:
    certainty: BurdenCertainty
    allocatedTo: str
    standardLabel: str
    sourceText: str
    caveat: str
    confidence: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class LimitationAnalysisSummary:
    applicablePeriodYears: int | None
    applicablePeriodLabel: str
    source: str
    accrualDate: str | None
    accrualFact: str
    currentDate: str | None
    expiryDate: str | None
    status: LimitationStatus
    tollingFactors: list[str] = field(default_factory=list)
    temporalResolution: dict[str, Any] = field(default_factory=dict)
    caveats: list[str] = field(default_factory=list)
    calculation: str = ""
    confidence: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BrainResult:
    answer_body: str
    suggested_citations: list[str]
    issue_map: list[BrainIssue]
    supporting_arguments: list[str]
    opposing_arguments: list[str]
    rebuttals: list[str]
    risk_flags: list[BrainRiskFlag]
    evidence_flags: list[BrainRiskFlag]
    missing_facts: list[str]
    recommended_next_actions: list[str]
    filtered_authorities: list[dict[str, Any]]
    suppressed_authorities: list[dict[str, Any]]
    dead_law_rewrites: list[str]
    graph_evidence: list[dict[str, Any]]
    memory_reads: list[dict[str, Any]]
    memory_write_proposal: list[dict[str, Any]]
    supervision_status: str
    model_usage: BrainModelUsage
    reasoning_framework: ReasoningFramework
    channel: BrainChannel
    spoken_summary_generated: bool = False

    def to_meta_dict(self) -> dict[str, Any]:
        return {
            "issueMap": [item.to_dict() for item in self.issue_map],
            "supportingArguments": list(self.supporting_arguments),
            "opposingArguments": list(self.opposing_arguments),
            "rebuttals": list(self.rebuttals),
            "riskFlags": [item.to_dict() for item in self.risk_flags],
            "evidenceFlags": [item.to_dict() for item in self.evidence_flags],
            "missingFacts": list(self.missing_facts),
            "recommendedNextActions": list(self.recommended_next_actions),
            "authoritySummary": {
                "authorityCount": len(self.filtered_authorities),
                "suppressedCount": len(self.suppressed_authorities),
            },
            "filteredAuthorities": list(self.filtered_authorities),
            "suppressedAuthorities": list(self.suppressed_authorities),
            "deadLawRewrites": list(self.dead_law_rewrites),
            "graphEvidence": list(self.graph_evidence),
            "memoryReads": list(self.memory_reads),
            "memoryWriteProposal": list(self.memory_write_proposal),
            "supervisionStatus": self.supervision_status,
            "modelUsage": self.model_usage.to_dict(),
            "rendering": {
                "issueFramework": "IRAC",
                "finalFramework": self.reasoning_framework,
                "channel": self.channel,
                "spokenSummaryGenerated": self.spoken_summary_generated,
            },
        }
