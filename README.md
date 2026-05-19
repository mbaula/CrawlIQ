# CrawlIQ

**CrawlIQ** is a Dockerized mini search engine: you supply a seed URL, run a bounded crawl, and pages move through fetch, extract, index, and search. It was made with **Next.js** (dashboard), **FastAPI** (API), **Python workers** (crawl + index), **PostgreSQL**, **Redis**, and **RQ** for jobs.

## Features

- **Bounded crawls** — seed URL, max pages/depth, same-domain filtering, robots.txt awareness, per-domain rate limiting
- **Job queue** — crawl work enqueued via Redis and processed by Python workers (RQ)
- **Indexing & search** — HTML fetch/parse, tokenization, BM25 ranking, snippets
- **Graph-enhanced search** — optional reranking using page-graph neighbors and duplicate signals (`graph_enhanced=true`)
- **Page graph** — link edges, URL hierarchy, content similarity, near-duplicate detection, and graph metrics (e.g. betweenness) per crawl job
- **Dashboard** — start and monitor crawl jobs, run search, explore graph health and subgraphs
- **Deterministic demo** — bundled `demo-site/` for reproducible local demos without hitting arbitrary external domains

## Quick start

From the repo root:

```bash
docker compose up --build
```

Migrations run automatically when the API container starts (`alembic upgrade head`).

| Service | URL |
| --- | --- |
| Web UI | http://localhost:3000 |
| API | http://localhost:8000 |
| API docs (Swagger) | http://localhost:8000/docs |
| Demo site | http://localhost:8081 |

## Screenshots

![Dashboard](img/preview-dashboard.png)

![Search](img/preview-search.png)

![Graph](img/preview-graph.png)

![Jobs](img/preview-jobs.png)

## API reference

With the stack running, interactive OpenAPI docs are at **http://localhost:8000/docs**

## Tests

From `apps/api`:

**Unit tests** (no Postgres required):

```bash
python -m pytest -m "not integration"
```

**Integration tests** (Postgres + migrations; marked `@pytest.mark.integration`):

```bash
# PowerShell
$env:CRAWLIQ_TEST_DATABASE_URL = "postgresql://crawliq:crawliq@localhost:5432/crawliq_test"
python -m pytest -m integration
```

Create the test database and run Alembic migrations before integration tests.

## Monorepo layout

| Path | Role |
|------|------|
| `apps/web` | Next.js + TypeScript + Tailwind (dashboard) |
| `apps/api` | FastAPI + Pydantic (HTTP API) |
| `apps/worker` | Python crawler, indexer, and queue consumers |
| `infra` | Docker Compose, Postgres/Redis config (filled in as the build progresses) |
| `demo-site/` | Static site for deterministic crawl demos |

## Prerequisites

- Docker and Docker Compose (recommended for local runs)
- Node.js 20+ (for `apps/web` without Docker)
- Python 3.11+ (for `apps/api` and `apps/worker` without Docker)

Optional API settings: see `apps/api/.env.example`.
