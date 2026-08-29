FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev

COPY apps ./apps
COPY packages ./packages
COPY proto ./proto
COPY rag_dataset_20docs ./rag_dataset_20docs
COPY LICENSE README.md SECURITY.md SOUL.md AGENTS.md ./
COPY docker-entrypoint.sh ./docker-entrypoint.sh

RUN groupadd --system agent-harness \
    && useradd --system --gid agent-harness --home-dir /home/agent-harness agent-harness \
    && chmod 0555 /app/docker-entrypoint.sh \
    && chown -R agent-harness:agent-harness /app

ENV PATH="/app/.venv/bin:${PATH}"

USER agent-harness

EXPOSE 8000 50051

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["uvicorn", "apps.api_gateway.main:app", "--host", "0.0.0.0", "--port", "8000"]
