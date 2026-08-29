from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import re
from typing import Any

from packages.rag.ingestion import AuthoritativeDocumentLoader


SUPPORTED_SUFFIXES = {".md": "text/markdown", ".json": "application/json", ".svg": "image/svg+xml", ".txt": "text/plain"}


def default_corpus_root() -> Path:
    configured = os.getenv("AGENT_HARNESS_RAG_ROOT")
    return Path(configured).expanduser().resolve() if configured else (Path.cwd() / "rag_dataset_20docs").resolve()


class AuthoritativeCorpus:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or default_corpus_root()).resolve()

    def search(self, query: str, *, limit: int = 8, include_superseded: bool = False) -> list[dict[str, Any]]:
        query = query.strip()
        if not query or not self.root.is_dir():
            return []
        hits = []
        for path in sorted(self.root.iterdir()):
            media_type = SUPPORTED_SUFFIXES.get(path.suffix.lower())
            if not path.is_file() or not path.name.startswith("DOC-") or not media_type:
                continue
            text = self._text(path)
            status = self._status(text)
            if status == "superseded" and not include_superseded:
                continue
            score = self._score(query, text, path.name)
            if score <= 0:
                continue
            version = self._version(path, text)
            hits.append({
                "doc_id": path.name.split("_", 1)[0], "title": self._title(path, text),
                "version": version, "status": status, "source_path": path.name,
                "source_ref": f"rag://rag_dataset_20docs/{path.name}",
                "content_hash": "sha256:" + sha256(path.read_bytes()).hexdigest(),
                "media_type": media_type, "snippet": self._snippet(text, query),
                "score": score + (10_000 if status == "active" else 0) - (2_000 if "BENCHMARK" in path.name.upper() else 0),
            })
        return sorted(hits, key=lambda item: (-item["score"], item["source_path"]))[: max(1, limit)]

    @staticmethod
    def _text(path: Path) -> str:
        raw = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            try:
                return json.dumps(json.loads(raw), ensure_ascii=False, indent=2)
            except json.JSONDecodeError:
                return raw
        if path.suffix.lower() == ".svg":
            return " ".join(re.findall(r">([^<>]+)<", raw))
        return raw

    @staticmethod
    def _status(text: str) -> str:
        return AuthoritativeDocumentLoader._status(text)

    @staticmethod
    def _version(path: Path, text: str) -> str:
        match = re.search(r"(?:版本号|版本|version)[^v\d]{0,12}(v?\d+(?:\.\d+)+)", text[:4000], re.I) or re.search(r"_v(\d+(?:\.\d+)+)", path.name, re.I)
        if match:
            value = match.group(1)
            return value if value.lower().startswith("v") else f"v{value}"
        return "unversioned"

    @staticmethod
    def _title(path: Path, text: str) -> str:
        if path.suffix.lower() == ".json":
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                meta = data.get("metadata") or data.get("dataset_metadata") or {}
                return str(meta.get("title") or meta.get("dataset_name") or path.stem)
            except (json.JSONDecodeError, AttributeError):
                pass
        match = re.search(r"^#\s+(.+)$", text, re.M)
        return match.group(1).strip() if match else path.stem

    @staticmethod
    def _score(query: str, text: str, name: str) -> int:
        haystack = (name + "\n" + text).lower()
        terms = {query.lower(), *re.findall(r"[a-z0-9_.-]{2,}|[\u4e00-\u9fff]{2,}", query.lower())}
        return sum(haystack.count(term) * max(1, len(term)) for term in terms if term)

    @staticmethod
    def _snippet(text: str, query: str) -> str:
        compact = re.sub(r"\s+", " ", text).strip()
        position = compact.lower().find(query.lower())
        if position < 0:
            position = 0
        start = max(0, position - 100)
        return compact[start : start + 500]
