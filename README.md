# CrawlIQ

CrawlIQ is a Dockerized mini search engine: you supply a seed URL, run a bounded crawl, and watch pages move through fetch, extract, index, and search. The stack is **Next.js** (dashboard), **FastAPI** (API), **Python workers** (crawl + index), **PostgreSQL**, **Redis**, and **RQ** for jobs.

This repository is a monorepo:

| Path | Role |
|------|------|
| `apps/web` | Next.js + TypeScript + Tailwind (dashboard) |
| `apps/api` | FastAPI + Pydantic (HTTP API) |
| `apps/worker` | Python crawler, indexer, and queue consumers |
| `infra` | Docker Compose, Postgres/Redis config (filled in as the build progresses) |
| `docs` | Architecture and design notes |

See `plan.md` for the full 2-week build plan and issue order.

## Prerequisites

- Docker and Docker Compose (recommended for local runs after Compose is added)
- Node.js 20+ (for `apps/web`)
- Python 3.11+ (for `apps/api` and `apps/worker`)

## Configuration

Copy `.env.example` to `.env` and adjust values for your environment. Required variables are documented inline in `.env.example`.

## License

Private / unspecified — set as needed for your portfolio.
