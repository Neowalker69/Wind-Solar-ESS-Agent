from datetime import datetime

from packages.session_search.base import ResourceSearchResult
from packages.storage.postgres_connection import ConnectionFactory


class PostgresResourceSearch:
    def __init__(self, connection_factory: ConnectionFactory) -> None:
        self.connection_factory = connection_factory

    def search(
        self,
        query: str | None = None,
        *,
        site_id: str | None = None,
        session_id: str | None = None,
        run_id: str | None = None,
        asset_id: str | None = None,
        device_id: str | None = None,
        model_id: str | None = None,
        tool_id: str | None = None,
        workflow_id: str | None = None,
        status: str | None = None,
        occurred_from: datetime | None = None,
        occurred_to: datetime | None = None,
        limit: int = 10,
    ) -> list[ResourceSearchResult]:
        filters = {
            "query": query,
            "site_id": site_id,
            "session_id": session_id,
            "run_id": run_id,
            "asset_id": asset_id,
            "device_id": device_id,
            "model_id": model_id,
            "tool_id": tool_id,
            "workflow_id": workflow_id,
            "status": status,
            "occurred_from": occurred_from,
            "occurred_to": occurred_to,
        }
        if not any(value is not None and value != "" for value in filters.values()):
            return []

        where: list[str] = []
        params = {
            key: value
            for key, value in filters.items()
            if value is not None and value != ""
        }
        if query:
            where.append(
                "("
                "to_tsvector('public.harness_zh', content) "
                "@@ plainto_tsquery('public.harness_zh', %(query)s) "
                "OR content ILIKE '%%' || %(query)s || '%%'"
                ")"
            )
        for field in (
            "site_id",
            "session_id",
            "run_id",
            "model_id",
            "tool_id",
            "workflow_id",
            "status",
        ):
            if filters[field]:
                where.append(f"{field} = %({field})s")
        for field in ("asset_id", "device_id"):
            if filters[field]:
                where.append(f"content ILIKE '%%' || %({field})s || '%%'")
        if occurred_from:
            where.append("occurred_at >= %(occurred_from)s")
        if occurred_to:
            where.append("occurred_at <= %(occurred_to)s")

        params["limit"] = max(1, min(limit, 50))
        score = (
            "ts_rank_cd("
            "to_tsvector('public.harness_zh', content), "
            "plainto_tsquery('public.harness_zh', %(query)s)"
            ")"
            if query
            else "0.0"
        )
        snippet = (
            "ts_headline("
            "'public.harness_zh', content, "
            "plainto_tsquery('public.harness_zh', %(query)s), "
            "'StartSel=<mark>, StopSel=</mark>, MaxFragments=2, MaxWords=24'"
            ")"
            if query
            else "left(content, 320)"
        )
        sql = f"""
            SELECT
                resource_type,
                resource_id,
                session_id,
                run_id,
                {snippet} AS snippet,
                occurred_at,
                {score} AS score
            FROM resource_search_documents
            WHERE {" AND ".join(where)}
            ORDER BY score DESC, occurred_at DESC
            LIMIT %(limit)s
        """
        with self.connection_factory() as connection:
            rows = connection.execute(sql, params).fetchall()
        return [
            ResourceSearchResult(
                resource_type=row["resource_type"],
                resource_id=str(row["resource_id"]),
                session_id=row["session_id"],
                run_id=row["run_id"],
                snippet=row["snippet"],
                occurred_at=row["occurred_at"],
                score=float(row["score"]),
            )
            for row in rows
        ]
