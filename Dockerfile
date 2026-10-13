# ── Stage 1: dependency builder ──────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: runtime image ────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Non-root user
RUN addgroup --system appgroup && adduser --system --ingroup appgroup appuser

# Copy installed packages from builder
COPY --from=builder /install /usr/local

# Copy application code only (secrets/tests/tools excluded via .dockerignore)
COPY app/ app/
COPY alembic/ alembic/
COPY alembic.ini .

# Bake the BM25 keyword model (fastembed "Qdrant/bm25", used in
# app/retrieval/pipeline.py) into the image at build time, so a fresh container
# does not download it on first ingestion. fastembed reads FASTEMBED_CACHE_PATH.
ENV FASTEMBED_CACHE_PATH=/opt/fastembed_cache
RUN python -c "from fastembed import SparseTextEmbedding; SparseTextEmbedding(model_name='Qdrant/bm25')" \
 && chown -R appuser:appgroup /opt/fastembed_cache

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
