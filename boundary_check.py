from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib


@dataclass(frozen=True)
class BoundaryCheckResult:
    ok: bool
    failures: tuple[str, ...]


WRAPPER_MODULES: tuple[str, ...] = (
    "crawler/conflict_detection.py",
    "crawler/legal_concepts.py",
    "crawler/ontology.py",
    "crawler/utils.py",
    "crawler/legal_tests.py",
    "crawler/element_materializer.py",
    "crawler/parsers/__init__.py",
    "crawler/parsers/act_text_parser.py",
    "crawler/parsers/statute_text_cleaner.py",
    "brain/models.py",
    "brain/procedural_history.py",
    "brain/practical_litigation.py",
    "brain/safety.py",
    "brain/source_safety.py",
    "brain/verification_gate.py",
    "brain/statute_context.py",
    "services/adverse_possession.py",
)

ADAPTER_MODULES: tuple[str, ...] = (
    "brain/dead_law_filter.py",
    "brain/distinguishing.py",
    "brain/synthesis_engine.py",
    "brain/authority_safety.py",
)

RUNTIME_SHARED_MARKERS: dict[str, tuple[str, ...]] = {
    "crawler/db.py": (
        "from shared.legal_corpus.store_contracts import LegalCorpusStore",
        "class CrawlerStore(LegalCorpusStore):",
    ),
    "crawler/pipeline.py": (
        "from shared.legal_corpus.crawler.pipeline_helpers import",
        "return shared_document_embed_eligible(document)",
        "return shared_combine_corpus_network_graphs(",
    ),
}

SHARED_REQUIRED_FILES: tuple[str, ...] = (
    "store_contracts.py",
    "brain/answer_contract.py",
    "brain/authority_safety.py",
    "brain/burden_certainty.py",
    "brain/case_strength.py",
    "brain/distinguishing.py",
    "brain/element_application.py",
    "crawler/conflict_detection.py",
    "crawler/legal_concepts.py",
    "crawler/ontology.py",
    "crawler/legal_tests.py",
    "crawler/element_materializer.py",
    "crawler/pipeline_helpers.py",
    "parsers/__init__.py",
    "parsers/act_text_parser.py",
    "parsers/statute_text_cleaner.py",
    "brain/models.py",
    "brain/procedural_history.py",
    "brain/practical_litigation.py",
    "brain/refusal_tracking.py",
    "brain/safety.py",
    "brain/source_safety.py",
    "brain/verification_gate.py",
    "brain/statute_context.py",
    "brain/statute_temporal.py",
    "brain/statute_verbatim.py",
    "brain/limitation_analysis.py",
    "brain/interpretation_bridge.py",
    "brain/stare_decisis.py",
    "brain/synthesis_core.py",
    "brain/dead_law_filter.py",
    "services/adverse_possession.py",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _backend_roots(repo_root: Path) -> tuple[Path, ...]:
    product_backend = repo_root / "backend"
    scraper_backend = repo_root / "Scrapper Ops center" / "backend"

    # Docker compose mounts the active backend at /app/backend and the shared
    # legal core at /app/shared. The source checkout's "Scrapper Ops center"
    # sibling is intentionally not present inside that runtime layout.
    if (
        product_backend.is_dir()
        and (repo_root / "shared" / "legal_corpus").is_dir()
        and not scraper_backend.exists()
    ):
        return (product_backend,)

    return (product_backend, scraper_backend)


def check_legal_core_boundary(repo_root: Path | str | None = None) -> BoundaryCheckResult:
    root = Path(repo_root or Path(__file__).resolve().parents[2]).resolve()
    shared_root = root / "shared" / "legal_corpus"
    backend_roots = _backend_roots(root)
    failures: list[str] = []

    for relative_path in SHARED_REQUIRED_FILES:
        if not (shared_root / relative_path).is_file():
            failures.append(f"missing shared legal-core file: shared/legal_corpus/{relative_path}")

    for backend_root in backend_roots:
        if not backend_root.is_dir():
            failures.append(f"missing backend root: {backend_root}")
            continue

        for relative_path in WRAPPER_MODULES:
            wrapper_path = backend_root / relative_path
            if not wrapper_path.is_file():
                failures.append(f"missing backend legal-core wrapper: {wrapper_path}")
                continue
            text = _read(wrapper_path)
            if "from shared.legal_corpus." not in text or "import *" not in text:
                failures.append(f"legal-rule wrapper no longer delegates to shared core: {wrapper_path}")
            if "def " in text or "class " in text:
                failures.append(f"legal-rule implementation reintroduced into wrapper: {wrapper_path}")

        for relative_path in ADAPTER_MODULES:
            adapter_path = backend_root / relative_path
            if not adapter_path.is_file():
                failures.append(f"missing backend runtime adapter: {adapter_path}")
                continue
            text = _read(adapter_path)
            if "from shared.legal_corpus." not in text:
                failures.append(f"runtime adapter is not backed by shared legal core: {adapter_path}")

        for relative_path, markers in RUNTIME_SHARED_MARKERS.items():
            runtime_path = backend_root / relative_path
            if not runtime_path.is_file():
                failures.append(f"missing runtime adapter module: {runtime_path}")
                continue
            text = _read(runtime_path)
            for marker in markers:
                if marker not in text:
                    failures.append(f"runtime adapter lost shared legal-core marker {marker!r}: {runtime_path}")

    if len(backend_roots) >= 2:
        product_backend, scraper_backend = backend_roots[:2]
        for relative_path in ("crawler/db.py", "crawler/pipeline.py"):
            left = product_backend / relative_path
            right = scraper_backend / relative_path
            if left.is_file() and right.is_file() and _sha256(left) != _sha256(right):
                failures.append(f"runtime adapter drift between product backend and scraper ops: {relative_path}")

    return BoundaryCheckResult(ok=not failures, failures=tuple(failures))


def assert_legal_core_boundary(repo_root: Path | str | None = None) -> None:
    result = check_legal_core_boundary(repo_root)
    if not result.ok:
        message = "Wakili legal-core boundary check failed:\n" + "\n".join(f"- {failure}" for failure in result.failures)
        raise RuntimeError(message)
