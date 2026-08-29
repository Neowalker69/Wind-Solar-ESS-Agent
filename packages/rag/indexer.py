from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Protocol

from pydantic import BaseModel, Field

from packages.rag.embedding import RagEmbeddingEncoder
from packages.rag.ingestion import (
    AuthoritativeDocumentLoader,
    MEDIA_TYPES,
    StructureAwareChunker,
)
from packages.rag.models import RagChunk, RagDocument


class RagIndexRepository(Protocol):
    def start_index_run(self, **values: Any) -> None: ...

    def replace_document(
        self,
        document: RagDocument,
        chunks: list[RagChunk],
        **values: Any,
    ) -> None: ...

    def mark_missing_documents(self, **values: Any) -> None: ...

    def finish_index_run(self, **values: Any) -> None: ...


class RagIndexReport(BaseModel):
    run_id: str
    corpus_id: str
    index_version: str
    status: str
    document_count: int
    chunk_count: int
    excluded_document_count: int
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    warnings: list[str] = Field(default_factory=list)


class CorpusIndexer:
    def __init__(
        self,
        repository: RagIndexRepository,
        encoder: RagEmbeddingEncoder,
        *,
        loader: AuthoritativeDocumentLoader | None = None,
        chunker: StructureAwareChunker | None = None,
        batch_size: int = 16,
    ) -> None:
        self.repository = repository
        self.encoder = encoder
        self.loader = loader or AuthoritativeDocumentLoader()
        self.chunker = chunker or StructureAwareChunker()
        self.batch_size = max(1, batch_size)

    def index_root(self, root: Path, *, corpus_id: str) -> RagIndexReport:
        root = root.resolve()
        paths = [
            path
            for path in sorted(root.iterdir())
            if path.is_file()
            and path.name.startswith("DOC-")
            and path.suffix.lower() in MEDIA_TYPES
        ] if root.is_dir() else []
        index_version = self._index_version(paths, corpus_id)
        run_id = f"rag_index_{index_version.removeprefix('idx_')}"
        self.repository.start_index_run(
            run_id=run_id,
            corpus_id=corpus_id,
            index_version=index_version,
            status="running",
            embedding_provider=self.encoder.provider,
            embedding_model=self.encoder.model_id,
            embedding_dimensions=self.encoder.dimensions,
            metadata={"root": str(root), "chunker_version": self.chunker.version},
        )
        document_count = 0
        chunk_count = 0
        excluded_count = 0
        warnings: list[str] = []
        active_sources: set[str] = set()
        try:
            for path in paths:
                document = self.loader.load(path, corpus_id=corpus_id)
                if not document.indexable:
                    excluded_count += 1
                    warnings.append(f"{path.name}:{document.exclusion_reason}")
                    continue
                chunks = self.chunker.chunk(document)
                embedded: list[RagChunk] = []
                for offset in range(0, len(chunks), self.batch_size):
                    batch = chunks[offset : offset + self.batch_size]
                    vectors = self.encoder.encode_documents([chunk.text for chunk in batch])
                    embedded.extend(
                        chunk.model_copy(update={"embedding": vector})
                        for chunk, vector in zip(batch, vectors, strict=True)
                    )
                self.repository.replace_document(
                    document,
                    embedded,
                    index_version=index_version,
                    embedding_provider=self.encoder.provider,
                    embedding_model=self.encoder.model_id,
                    embedding_dimensions=self.encoder.dimensions,
                )
                document_count += 1
                chunk_count += len(embedded)
                active_sources.add(document.source_path)
            self.repository.mark_missing_documents(
                corpus_id=corpus_id,
                source_paths=active_sources,
                index_version=index_version,
            )
            report = RagIndexReport(
                run_id=run_id,
                corpus_id=corpus_id,
                index_version=index_version,
                status="completed",
                document_count=document_count,
                chunk_count=chunk_count,
                excluded_document_count=excluded_count,
                embedding_provider=self.encoder.provider,
                embedding_model=self.encoder.model_id,
                embedding_dimensions=self.encoder.dimensions,
                warnings=warnings,
            )
            self.repository.finish_index_run(
                **report.model_dump(exclude={"corpus_id", "index_version", "embedding_provider", "embedding_model", "embedding_dimensions", "warnings"}),
                error_code=None,
                metadata={"warnings": warnings},
            )
            return report
        except Exception as exc:
            self.repository.finish_index_run(
                run_id=run_id,
                status="failed",
                document_count=document_count,
                chunk_count=chunk_count,
                excluded_document_count=excluded_count,
                error_code=str(getattr(exc, "error_code", exc.__class__.__name__)),
                metadata={"warnings": warnings},
            )
            raise

    def _index_version(self, paths: list[Path], corpus_id: str) -> str:
        digest = sha256()
        digest.update(corpus_id.encode())
        digest.update(self.chunker.version.encode())
        digest.update(self.encoder.provider.encode())
        digest.update(self.encoder.model_id.encode())
        digest.update(str(self.encoder.dimensions).encode())
        for path in paths:
            digest.update(path.name.encode())
            digest.update(sha256(path.read_bytes()).digest())
        return "idx_" + digest.hexdigest()[:24]
