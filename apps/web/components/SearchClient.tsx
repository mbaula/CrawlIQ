"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { searchPages, type SearchResponse, type SearchResultItem } from "@/lib/api";

type Props = {
  initialQuery: string;
  initialJobId: number | null;
};

function parseJobId(raw: string | null): number | null {
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.floor(n);
}

function formatScore(score: number) {
  if (!Number.isFinite(score)) return "—";
  return score.toFixed(3);
}

function formatLatency(ms: number) {
  if (!Number.isFinite(ms)) return "—";
  return `${ms} ms`;
}

function TermPill({ term }: { term: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-rule bg-paper px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-muted">
      {term}
    </span>
  );
}

function ResultCard({ item }: { item: SearchResultItem }) {
  return (
    <article className="rounded border border-rule bg-paper p-5 shadow-lift transition-colors duration-200">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <h3 className="font-serif text-xl font-medium tracking-tight text-ink">
            {item.title ?? "Untitled page"}
          </h3>
          <a
            className="mt-1 block max-w-full truncate font-mono text-xs text-accent underline decoration-rule underline-offset-4 hover:decoration-accent"
            href={item.url}
            target="_blank"
            rel="noreferrer"
            title={item.url}
          >
            {item.url}
          </a>
        </div>
        <div className="flex shrink-0 items-baseline gap-3 font-mono text-xs text-muted">
          <span className="uppercase tracking-widest">Score</span>
          <span className="text-ink">{formatScore(item.score)}</span>
        </div>
      </div>
      <p className="mt-4 text-sm leading-relaxed text-muted">{item.snippet || "—"}</p>
      {item.matched_terms.length > 0 ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {item.matched_terms.map((term) => (
            <TermPill key={term} term={term} />
          ))}
        </div>
      ) : null}
    </article>
  );
}

export function SearchClient({ initialQuery, initialJobId }: Props) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [jobIdText, setJobIdText] = useState(initialJobId ? String(initialJobId) : "");
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);

  const lastRequestKeyRef = useRef<string>("");

  const jobId = useMemo(() => parseJobId(jobIdText), [jobIdText]);
  const trimmedQuery = useMemo(() => query.trim(), [query]);

  const requestKey = useMemo(() => {
    const parts = [trimmedQuery, jobId ? String(jobId) : ""];
    return parts.join("|");
  }, [trimmedQuery, jobId]);

  async function runSearch(nextQuery: string, nextJobId: number | null) {
    const q = nextQuery.trim();
    if (!q) {
      setData(null);
      setErrorMessage("Enter a query to search indexed pages.");
      return;
    }

    setLoading(true);
    setErrorMessage(null);

    const nextKey = `${q}|${nextJobId ?? ""}`;
    lastRequestKeyRef.current = nextKey;

    try {
      const response = await searchPages({ q, job_id: nextJobId ?? undefined, limit: 20 });
      if (lastRequestKeyRef.current !== nextKey) return;
      setData(response);
    } catch (error) {
      if (lastRequestKeyRef.current !== nextKey) return;
      setData(null);
      setErrorMessage(error instanceof Error ? error.message : "Search failed.");
    } finally {
      if (lastRequestKeyRef.current === nextKey) setLoading(false);
    }
  }

  function updateUrl(nextQuery: string, nextJobId: number | null) {
    const url = new URL(window.location.href);
    if (nextQuery.trim()) url.searchParams.set("q", nextQuery.trim());
    else url.searchParams.delete("q");
    if (nextJobId) url.searchParams.set("job_id", String(nextJobId));
    else url.searchParams.delete("job_id");
    router.replace(`${url.pathname}${url.search}`);
  }

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    updateUrl(query, jobId);
    await runSearch(query, jobId);
  }

  useEffect(() => {
    if (!initialQuery.trim()) return;
    runSearch(initialQuery, initialJobId).catch(() => {
      // initial load should not be noisy
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const headerMeta = useMemo(() => {
    if (!data) return null;
    return (
      <p className="mt-4 font-mono text-[11px] uppercase tracking-[0.2em] text-muted">
        <span className="text-ink">{data.result_count}</span> results ·{" "}
        <span className="text-ink">{formatLatency(data.latency_ms)}</span>
        {jobId ? (
          <>
            <span className="px-2 text-rule">·</span>
            <span>
              job <span className="text-ink">{jobId}</span>
            </span>
          </>
        ) : null}
      </p>
    );
  }, [data, jobId]);

  return (
    <section className="mt-8 space-y-6">
      <form onSubmit={onSubmit} className="rounded border border-rule bg-paper p-5 shadow-lift transition-colors duration-200">
        <div className="grid gap-4 sm:grid-cols-[1fr_12rem_auto] sm:items-end">
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-widest text-muted" htmlFor="query">
              Query
            </label>
            <input
              id="query"
              name="query"
              type="text"
              placeholder="fastapi async"
              className="mt-2 w-full rounded border border-rule bg-paper px-3 py-2 text-sm text-ink shadow-lift outline-none transition-colors focus:border-accent"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              required
            />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-widest text-muted" htmlFor="job-id">
              Job id (optional)
            </label>
            <input
              id="job-id"
              name="job-id"
              type="text"
              inputMode="numeric"
              placeholder="123"
              className="mt-2 w-full rounded border border-rule bg-paper px-3 py-2 text-sm text-ink shadow-lift outline-none transition-colors focus:border-accent"
              value={jobIdText}
              onChange={(e) => setJobIdText(e.target.value)}
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="h-10 rounded bg-accent px-4 text-sm font-medium text-paper shadow-lift transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:bg-rule"
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </div>

        <div className="mt-4 flex flex-wrap items-center gap-3 text-xs text-muted">
          <span className="font-mono uppercase tracking-widest">Tips</span>
          <span>Use keywords for best results.</span>
          <span className="text-rule">·</span>
          <Link
            href="/jobs"
            className="text-accent underline decoration-rule underline-offset-4 hover:decoration-accent"
          >
            Browse jobs
          </Link>
        </div>
      </form>

      {headerMeta}

      {errorMessage ? (
        <section className="rounded border border-danger/40 bg-danger/10 p-4 text-sm text-ink">
          <p className="font-medium">Search error</p>
          <p className="mt-1 text-xs text-muted">{errorMessage}</p>
        </section>
      ) : null}

      {loading && !data ? (
        <section className="border border-dashed border-rule bg-paper p-8 shadow-lift transition-colors duration-200">
          <p className="font-mono text-xs text-muted">Running query…</p>
        </section>
      ) : null}

      {!loading && data && data.result_count === 0 ? (
        <EmptyState
          title="No results"
          description="Try different terms, or run a crawl and wait for pages to be indexed."
        />
      ) : null}

      {data && data.result_count > 0 ? (
        <section className="space-y-4">
          {data.results.map((item) => (
            <ResultCard key={item.page_id} item={item} />
          ))}
        </section>
      ) : null}
    </section>
  );
}

