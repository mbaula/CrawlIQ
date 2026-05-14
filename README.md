# CrawlIQ

CrawlIQ is a Dockerized mini search engine: you supply a seed URL, run a bounded crawl, and watch pages move through fetch, extract, index, and search. The stack is **Next.js** (dashboard), **FastAPI** (API), **Python workers** (crawl + index), **PostgreSQL**, **Redis**, and **RQ** for jobs.

This repository is a monorepo:

| Path | Role |
|------|------|
| `apps/web` | Next.js + TypeScript + Tailwind (dashboard) |
| `apps/api` | FastAPI + Pydantic (HTTP API) |
| `apps/worker` | Python crawler, indexer, and queue consumers |
| `infra` | Docker Compose, Postgres/Redis config (filled in as the build progresses) |
| `docs` | Architecture notes: [glossary](docs/glossary.md), [formulas](docs/formulas.md), [page graph](docs/page-graph-design.md) |

## Page graph (Sprint 9)

After migrations through **`0007_page_graph_tables`**, populate per-job graph data without recrawling: **`POST /crawl-jobs/{id}/graph/link-edges`**, **`.../url-hierarchy-edges`**, **`.../content-similarity-edges`**, **`.../near-duplicate-edges`**, and **`.../graph/compute-metrics`**. Read slices with **`GET /graph/subgraph`**, **`GET /pages/{page_id}/neighbors`**, **`GET /pages/{page_id}/graph`**, **`GET /graph/stats`**, **`GET /graph/clusters`** (all require `job_id`). See **`docs/page-graph-design.md`** and **`article.md`** (Sprint 9).

## Prerequisites

- Docker and Docker Compose (recommended for local runs after Compose is added)
- Node.js 20+ (for `apps/web`)
- Python 3.11+ (for `apps/api` and `apps/worker`)

## Running tests

### API unit tests (fast, no Postgres required)

From `apps/api`:

```bash
python -m pytest -m "not integration"
```

### API integration tests (requires Postgres + migrations)

Integration tests are marked with `@pytest.mark.integration` and require a real Postgres database URL in:

```text
CRAWLIQ_TEST_DATABASE_URL
```

Example:

```bash
$env:CRAWLIQ_TEST_DATABASE_URL = "postgresql://crawliq:crawliq@localhost:${POSTGRES_PORT:-5432}/crawliq_test"
python -m pytest -m integration
```

Notes:
- If you already have a local Postgres running on `5432`, start the Docker Postgres on a different port:
  - `POSTGRES_PORT=5433 docker compose up -d postgres`
  - then use `localhost:5433` in `CRAWLIQ_TEST_DATABASE_URL`
- Create the database and apply Alembic migrations before running integration tests.
- The suite uses `httpx.MockTransport` for deterministic HTTP behavior; no external calls are required.

## Demo site (deterministic crawl target)

This repo includes a small static website at `demo-site/` so you can demo crawling + indexing + search without hitting random external domains.

### Run the demo site

```bash
docker compose up -d demo-site
```

It will be available at:

```text
http://localhost:8081/
```

### Suggested demo crawl

- **Seed URL**: `http://demo-site/` (from inside Docker) or `http://localhost:8081/` (from your host)
- **Max pages**: `25`
- **Max depth**: `3`
- **Same-domain only**: `true`

If you run the full stack with Docker Compose, the worker crawls from inside the network, so using `http://demo-site/` is the most reliable seed.
