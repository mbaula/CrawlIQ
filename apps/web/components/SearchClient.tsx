"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { searchPages, type RelatedPageRead, type SearchResponse, type SearchResultItem } from "@/lib/api";

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
      {(item.related ?? []).length > 0 ? <RelatedBlock related={item.related ?? []} /> : null}
      {item.score_explanation ? (
        <details className="mt-3 rounded border border-rule/80 bg-paper px-3 py-2 text-xs text-muted">
          <summary className="cursor-pointer font-mono text-[10px] uppercase tracking-widest text-muted">
            Graph score breakdown
          </summary>
          <p className="mt-2 whitespace-pre-wrap font-mono text-[11px] leading-relaxed text-ink">{item.score_explanation}</p>
          {item.score_components ? (
            <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-1 font-mono text-[10px] text-muted sm:grid-cols-4">
              <dt>bm25_norm</dt>
              <dd className="text-ink">{item.score_components.bm25_norm.toFixed(3)}</dd>
              <dt>PR_norm</dt>
              <dd className="text-ink">{item.score_components.pagerank_norm.toFixed(3)}</dd>
              <dt>neighbor</dt>
              <dd className="text-ink">{item.score_components.neighbor_boost_norm.toFixed(3)}</dd>
              <dt>dup_norm</dt>
              <dd className="text-ink">{item.score_components.duplicate_penalty_norm.toFixed(3)}</dd>
            </dl>
          ) : null}
        </details>
      ) : null}
    </article>
  );
}

function RelatedBlock({ related }: { related: RelatedPageRead[] }) {
  return (
    <div className="mt-4 border-t border-rule pt-4">
      <p className="font-mono text-[10px] uppercase tracking-[0.2em] text-muted">Related pages</p>
      <ul className="mt-2 space-y-3">
        {related.map((rel) => (
          <li key={rel.page_id} className="rounded border border-rule/80 bg-paper px-3 py-2">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <a
                href={rel.url}
                target="_blank"
                rel="noreferrer"
                className="min-w-0 flex-1 truncate text-sm font-medium text-accent underline decoration-rule underline-offset-4 hover:decoration-accent"
                title={rel.url}
              >
                {rel.title ?? "Untitled page"}
              </a>
              <span className="shrink-0 font-mono text-[10px] uppercase tracking-widest text-muted">
                {rel.edge_type.replace(/_/g, " ")}
              </span>
            </div>
            <p className="mt-1 text-xs leading-snug text-muted">{rel.reason}</p>
            <p className="mt-1 font-mono text-[10px] text-rule">
              strength <span className="text-ink">{rel.strength.toFixed(4)}</span>
            </p>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SearchClient({ initialQuery, initialJobId }: Props) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [jobIdText, setJobIdText] = useState(initialJobId ? String(initialJobId) : "");
  const [includeRelated, setIncludeRelated] = useState(Boolean(initialJobId));
  const [graphEnhanced, setGraphEnhanced] = useState(false);
  const [relatedLimit, setRelatedLimit] = useState(3);
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);

  const lastRequestKeyRef = useRef<string>("");

  const jobId = useMemo(() => parseJobId(jobIdText), [jobIdText]);
  const trimmedQuery = useMemo(() => query.trim(), [query]);

  useEffect(() => {
    if (!jobId) {
      setIncludeRelated(false);
      setGraphEnhanced(false);
    }
  }, [jobId]);

  const requestKey = useMemo(() => {
    const parts = [
      trimmedQuery,
      jobId ? String(jobId) : "",
      jobId && includeRelated ? "rel1" : "rel0",
      jobId && includeRelated ? String(relatedLimit) : "",
      jobId && graphEnhanced ? "g1" : "g0",
    ];
    return parts.join("|");
  }, [trimmedQuery, jobId, includeRelated, relatedLimit, graphEnhanced]);

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
      const useRelated = Boolean(nextJobId && includeRelated);
      const useGraph = Boolean(nextJobId && graphEnhanced);
      const rl = Math.min(10, Math.max(1, relatedLimit));
      const response = await searchPages({
        q,
        job_id: nextJobId ?? undefined,
        limit: 20,
        include_related: useRelated,
        related_limit: useRelated ? rl : undefined,
        graph_enhanced: useGraph,
      });
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

        <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-rule text-accent focus:ring-accent"
              checked={includeRelated && Boolean(jobId)}
              disabled={!jobId}
              onChange={(e) => setIncludeRelated(e.target.checked)}
            />
            <span>
              Include related pages from the crawl graph{" "}
              {!jobId ? <span className="text-rule">(enter a job id)</span> : null}
            </span>
          </label>
          {jobId && includeRelated ? (
            <label className="flex items-center gap-2 font-mono text-[11px] text-muted">
              <span className="uppercase tracking-widest">Related limit</span>
              <input
                type="number"
                min={1}
                max={10}
                className="w-14 rounded border border-rule bg-paper px-2 py-1 text-xs text-ink"
                value={relatedLimit}
                onChange={(e) => {
                  const n = Number(e.target.value);
                  if (!Number.isFinite(n)) return;
                  setRelatedLimit(Math.min(10, Math.max(1, Math.floor(n))));
                }}
              />
            </label>
          ) : null}
        </div>

        <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <label className="flex cursor-pointer items-center gap-2 text-xs text-muted">
            <input
              type="checkbox"
              className="h-4 w-4 rounded border-rule text-accent focus:ring-accent"
              checked={graphEnhanced && Boolean(jobId)}
              disabled={!jobId}
              onChange={(e) => setGraphEnhanced(e.target.checked)}
            />
            <span>
              Graph-enhanced ranking (BM25 + PageRank + neighbors){" "}
              {!jobId ? <span className="text-rule">(enter a job id)</span> : null}
            </span>
          </label>
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

