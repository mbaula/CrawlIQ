# Pin Debian Bookworm: `python:3.12-slim` can track testing (e.g. trixie) and hit
# transient `Hash Sum mismatch` on deb.debian.org during `apt-get update`.
# Build from repo root: ``docker compose build api`` (context ``.``, this file ``apps/api/Dockerfile``).
FROM python:3.12-slim-bookworm

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PYTHONPATH=/packages

WORKDIR /app

# Fresh CA bundle + current pip (fewer TLS / middlebox issues on some networks).
RUN rm -rf /var/lib/apt/lists/* \
    && apt-get update \
        -o Acquire::Retries=6 \
        -o Acquire::http::No-Cache=true \
        -o Acquire::Check-Valid-Until=false \
    && apt-get install -y --no-install-recommends ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY apps/api/requirements.txt .

ARG PIP_INDEX_URL=https://pypi.org/simple
ARG PIP_EXTRA_TRUSTED_HOST=
RUN pip install --no-cache-dir --upgrade pip setuptools wheel \
    && pip install --no-cache-dir \
        --index-url "${PIP_INDEX_URL}" \
        --trusted-host pypi.org \
        --trusted-host files.pythonhosted.org \
        --trusted-host pypi.python.org \
        $( [ -z "${PIP_EXTRA_TRUSTED_HOST}" ] || echo "--trusted-host ${PIP_EXTRA_TRUSTED_HOST}" ) \
        --retries 10 \
        --timeout 120 \
        -r requirements.txt

# Shared crawl package (import as ``crawliq_core`` via PYTHONPATH=/packages).
# Copied after pip install so edits to shared code don't invalidate the dep layer.
COPY packages /packages

COPY apps/api/alembic.ini ./
COPY apps/api/alembic ./alembic
COPY apps/api/db ./db
COPY apps/api/models ./models
COPY apps/api/routers ./routers
COPY apps/api/schemas ./schemas
COPY apps/api/services ./services
COPY apps/api/config.py apps/api/main.py .

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && exec uvicorn main:app --host 0.0.0.0 --port 8000"]
