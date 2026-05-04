import os

from fastapi import FastAPI

app = FastAPI(title="CrawlIQ API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "crawliq-api"}


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "CrawlIQ API"}
