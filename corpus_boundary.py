from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from pathlib import Path


SCRAPER_OPS_DIR_NAME = "scrapper ops center"
PRODUCT_BACKEND_ROLE = "product_backend"
SCRAPER_OPS_ROLE = "scraper_ops_corpus_authority"
UNKNOWN_ROLE = "unknown_backend"
SHARED_CORPUS_OWNER = "shared_legal_corpus"

LEGAL_SAFETY_MODULES: tuple[str, ...] = (
    "brain/dead_law_filter.py",
    "brain/statute_context.py",
    "brain/synthesis_engine.py",
    "brain/verification_gate.py",
    "crawler/conflict_detection.py",
    "crawler/element_materializer.py",
    "crawler/pipeline.py",
    "crawler/db.py",
)


@dataclass(frozen=True, slots=True)
class ModuleParity:
    relative_path: str
    product_path: Path
    scraper_ops_path: Path
    product_exists: bool
    scraper_ops_exists: bool
    product_sha256: str | None
    scraper_ops_sha256: str | None

    @property
    def in_sync(self) -> bool:
        return (
            self.product_exists
            and self.scraper_ops_exists
            and self.product_sha256 is not None
            and self.product_sha256 == self.scraper_ops_sha256
        )


@dataclass(frozen=True, slots=True)
class CorpusBoundary:
    role: str
    workspace_root: Path
    current_backend_dir: Path
    product_backend_dir: Path
    scraper_ops_backend_dir: Path
    canonical_code_backend_dir: Path
    live_db_path: Path
    chroma_dir: Path
    bootstrap_db_path: Path | None
    ops_data_dir: Path
    corpus_owner: str
    shared_legal_corpus_dir: Path

    @property
    def is_scraper_ops_runtime(self) -> bool:
        return self.role == SCRAPER_OPS_ROLE


def backend_role(backend_dir: Path) -> str:
    resolved = backend_dir.resolve()
    parent_name = resolved.parent.name.strip().lower()
    if parent_name == SCRAPER_OPS_DIR_NAME:
        return SCRAPER_OPS_ROLE
    if resolved.name.strip().lower() == "backend":
        return PRODUCT_BACKEND_ROLE
    return UNKNOWN_ROLE


def workspace_root_for_backend(backend_dir: Path) -> Path:
    resolved = backend_dir.resolve()
    repo_root = resolved.parent
    if repo_root.name.strip().lower() == SCRAPER_OPS_DIR_NAME:
        return repo_root.parent.resolve()
    return repo_root.resolve()


def product_backend_dir_for(workspace_root: Path) -> Path:
    return workspace_root.resolve() / "backend"


def scraper_ops_backend_dir_for(workspace_root: Path) -> Path:
    return workspace_root.resolve() / "Scrapper Ops center" / "backend"


def shared_legal_corpus_dir_for(workspace_root: Path) -> Path:
    return workspace_root.resolve() / "shared" / "legal_corpus"


def scraper_ops_bootstrap_db_for(workspace_root: Path) -> Path | None:
    candidate = scraper_ops_backend_dir_for(workspace_root) / "bootstrap-data" / "crawler.bootstrap.db"
    return candidate.resolve() if candidate.exists() else None


def _path_from_env(name: str) -> Path | None:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return None
    return Path(raw_value).expanduser().resolve()


def canonical_code_backend_dir(workspace_root: Path) -> Path:
    owner = os.getenv("WAKILI_CORPUS_CODE_OWNER", SHARED_CORPUS_OWNER).strip().lower()
    product_dir = product_backend_dir_for(workspace_root)
    ops_dir = scraper_ops_backend_dir_for(workspace_root)
    shared_dir = shared_legal_corpus_dir_for(workspace_root)
    if owner in {"root", "product", "backend", "wakili"}:
        return product_dir.resolve()
    if owner in {"scraper_ops", "ops", "scrapper_ops"} and ops_dir.exists():
        return ops_dir.resolve()
    return shared_dir.resolve()


def default_live_db_path(backend_dir: Path) -> Path:
    workspace_root = workspace_root_for_backend(backend_dir)

    explicit = _path_from_env("CRAWLER_DB_PATH") or _path_from_env("WAKILI_CORPUS_DB_PATH")
    if explicit is not None:
        return explicit

    docker_ops_data = Path("/app/ops-data/crawler.db")
    if docker_ops_data.exists():
        return docker_ops_data.resolve()

    workspace_ops_data = scraper_ops_backend_dir_for(workspace_root) / "ops-data" / "crawler.db"
    if workspace_ops_data.exists():
        return workspace_ops_data.resolve()

    return (product_backend_dir_for(workspace_root) / "data" / "crawler.db").resolve()


def default_chroma_dir(backend_dir: Path) -> Path:
    explicit = _path_from_env("WAKILI_CORPUS_CHROMA_DIR")
    if explicit is not None:
        return explicit
    return (workspace_root_for_backend(backend_dir) / "chroma_db").resolve()


def resolve_corpus_boundary(backend_dir: Path) -> CorpusBoundary:
    resolved_backend = backend_dir.resolve()
    workspace_root = workspace_root_for_backend(resolved_backend)
    product_dir = product_backend_dir_for(workspace_root).resolve()
    ops_dir = scraper_ops_backend_dir_for(workspace_root).resolve()
    shared_dir = shared_legal_corpus_dir_for(workspace_root).resolve()
    return CorpusBoundary(
        role=backend_role(resolved_backend),
        workspace_root=workspace_root,
        current_backend_dir=resolved_backend,
        product_backend_dir=product_dir,
        scraper_ops_backend_dir=ops_dir,
        canonical_code_backend_dir=canonical_code_backend_dir(workspace_root),
        live_db_path=default_live_db_path(resolved_backend),
        chroma_dir=default_chroma_dir(resolved_backend),
        bootstrap_db_path=scraper_ops_bootstrap_db_for(workspace_root),
        ops_data_dir=(ops_dir / "ops-data").resolve(),
        corpus_owner=os.getenv("WAKILI_CORPUS_CODE_OWNER", SHARED_CORPUS_OWNER).strip().lower() or SHARED_CORPUS_OWNER,
        shared_legal_corpus_dir=shared_dir,
    )


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def legal_safety_module_parity(
    workspace_root: Path,
    modules: tuple[str, ...] = LEGAL_SAFETY_MODULES,
) -> tuple[ModuleParity, ...]:
    product_dir = product_backend_dir_for(workspace_root)
    ops_dir = scraper_ops_backend_dir_for(workspace_root)
    results: list[ModuleParity] = []
    for relative_path in modules:
        product_path = product_dir / relative_path
        ops_path = ops_dir / relative_path
        results.append(
            ModuleParity(
                relative_path=relative_path,
                product_path=product_path.resolve(),
                scraper_ops_path=ops_path.resolve(),
                product_exists=product_path.exists(),
                scraper_ops_exists=ops_path.exists(),
                product_sha256=_sha256(product_path),
                scraper_ops_sha256=_sha256(ops_path),
            )
        )
    return tuple(results)


def legal_safety_drift(workspace_root: Path) -> tuple[ModuleParity, ...]:
    return tuple(item for item in legal_safety_module_parity(workspace_root) if not item.in_sync)
