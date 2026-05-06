FROM python:3.12-slim-bookworm

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DEFAULT_TIMEOUT=120 \
    PYTHONPATH=/packages

WORKDIR /app

RUN rm -rf /var/lib/apt/lists/* \
    && apt-get update \
        -o Acquire::Retries=6 \
        -o Acquire::http::No-Cache=true \
        -o Acquire::Check-Valid-Until=false \
    && apt-get install -y --no-install-recommends ca-certificates \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

COPY packages /packages

COPY apps/api/requirements.txt ./requirements-api.txt

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
        -r requirements-api.txt

COPY apps/api/db ./db
COPY apps/api/models ./models
COPY apps/api/schemas ./schemas
COPY apps/api/services ./services
COPY apps/api/config.py ./config.py
COPY apps/worker/jobs.py ./jobs.py
COPY apps/worker/main.py ./main.py

CMD ["python", "main.py"]
