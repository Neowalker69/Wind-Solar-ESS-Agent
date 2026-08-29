from __future__ import annotations

from hashlib import sha256
import json
from pathlib import Path
import re

from packages.rag.models import RagChunk, RagDocument


MEDIA_TYPES = {
    ".md": "text/markdown",
    ".txt": "text/plain",
    ".json": "application/json",
    ".svg": "image/svg+xml",
    ".png": "image/png",
}
INDEXABLE_MEDIA_TYPES = {
    "text/markdown",
    "text/plain",
    "application/json",
    "image/svg+xml",
}


class AuthoritativeDocumentLoader:
    def load(self, path: Path, *, corpus_id: str) -> RagDocument:
        media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
        content_hash = "sha256:" + sha256(path.read_bytes()).hexdigest()
        exclusion_reason: str | None = None
        if "BENCHMARK" in path.name.upper():
            exclusion_reason = "evaluation_fixture"
        elif media_type not in INDEXABLE_MEDIA_TYPES:
            exclusion_reason = f"unsupported_media_type:{media_type}"
        text = self._text(path, media_type) if exclusion_reason is None else ""
        return RagDocument(
            corpus_id=corpus_id,
            document_id=path.stem.split("_", 1)[0],
            source_path=path.name,
            source_ref=f"rag://{corpus_id}/{path.name}",
            title=self._title(path, text),
            version=self._version(path, text),
            status=self._status(text),
            media_type=media_type,
            content_hash=content_hash,
            text=text,
            indexable=exclusion_reason is None,
            exclusion_reason=exclusion_reason,
        )

    @staticmethod
    def _text(path: Path, media_type: str) -> str:
        raw = path.read_text(encoding="utf-8")
        if media_type == "application/json":
            try:
                return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return raw
        if media_type == "image/svg+xml":
            return "\n".join(re.findall(r">([^<>]+)<", raw))
        return raw

    @staticmethod
    def _title(path: Path, text: str) -> str:
        match = re.search(r"^#\s+(.+)$", text, re.MULTILINE)
        return match.group(1).strip() if match else path.stem

    @staticmethod
    def _version(path: Path, text: str) -> str:
        match = re.search(
            r"(?:版本号|版本|version)[^v\d]{0,12}(v?\d+(?:\.\d+)+)",
            text[:4000],
            re.IGNORECASE,
        ) or re.search(r"_v(\d+(?:\.\d+)+)", path.name, re.IGNORECASE)
        if not match:
            return "unversioned"
        value = match.group(1)
        return value if value.lower().startswith("v") else f"v{value}"

    @staticmethod
    def _status(text: str) -> str:
        prefix = text[:3000]
        status_lines = "\n".join(
            line
            for line in prefix.splitlines()[:40]
            if re.search(r"版本号|生效状态|文档状态|版本状态|^\s*状态\s*[:：]", line, re.IGNORECASE)
        )
        explicit = status_lines.upper()
        if "ACTIVE" in explicit or "现行有效" in status_lines:
            return "active"
        if (
            "SUPERSEDED" in explicit
            or "已废止" in status_lines
            or "历史作废" in status_lines
        ):
            return "superseded"
        upper = prefix.upper()
        if "现行有效版本" in prefix or re.search(r"\bSTATUS\s*:\s*ACTIVE\b", upper):
            return "active"
        if (
            "SUPERSEDED" in upper
            or "已废止" in prefix
            or "历史作废" in prefix
        ):
            return "superseded"
        return "unspecified"


class StructureAwareChunker:
    version = "heading-v1"

    def __init__(self, *, max_chars: int = 1200, overlap_chars: int = 120) -> None:
        if max_chars < 32:
            raise ValueError("rag_chunk_size_too_small")
        self.max_chars = max_chars
        self.overlap_chars = max(0, min(overlap_chars, max_chars // 2))

    def chunk(self, document: RagDocument) -> list[RagChunk]:
        if not document.indexable or not document.text.strip():
            return []
        sections = self._sections(document.text)
        chunks: list[RagChunk] = []
        for heading, start_line, lines in sections:
            text = "\n".join(lines).strip()
            if not text:
                continue
            cursor = 0
            while cursor < len(text):
                end = min(len(text), cursor + self.max_chars)
                value = text[cursor:end].strip()
                if not value:
                    break
                ordinal = len(chunks)
                chunk_hash = "sha256:" + sha256(value.encode("utf-8")).hexdigest()
                chunk_id = "chunk_" + sha256(
                    f"{document.corpus_id}|{document.source_path}|{document.content_hash}|{self.version}|{ordinal}|{chunk_hash}".encode()
                ).hexdigest()[:24]
                relative_start = text[:cursor].count("\n")
                relative_end = text[:end].count("\n")
                chunks.append(
                    RagChunk(
                        chunk_id=chunk_id,
                        corpus_id=document.corpus_id,
                        document_id=document.document_id,
                        ordinal=ordinal,
                        heading=heading,
                        line_start=start_line + relative_start,
                        line_end=start_line + relative_end,
                        text=value,
                        content_hash=chunk_hash,
                        token_count=max(1, (len(value) + 3) // 4),
                        source_ref=f"{document.source_ref}#chunk={chunk_id}",
                        metadata={"chunker_version": self.version},
                    )
                )
                if end >= len(text):
                    break
                cursor = max(cursor + 1, end - self.overlap_chars)
        return chunks

    @staticmethod
    def _sections(text: str) -> list[tuple[str | None, int, list[str]]]:
        sections: list[tuple[str | None, int, list[str]]] = []
        heading: str | None = None
        start_line = 1
        lines: list[str] = []
        for line_number, line in enumerate(text.splitlines(), start=1):
            match = re.match(r"^#{1,6}\s+(.+?)\s*$", line)
            if match:
                if lines:
                    sections.append((heading, start_line, lines))
                heading = match.group(1).strip()
                start_line = line_number
                lines = [line]
            else:
                lines.append(line)
        if lines:
            sections.append((heading, start_line, lines))
        return sections
