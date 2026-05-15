"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";

import { EmptyState } from "@/components/EmptyState";
import { RelationshipMapModal } from "@/components/RelationshipMapModal";
import {
  searchPages,
  type GraphScoreComponentsRead,
  type RelatedPageRead,
  type SearchResponse,
  type SearchResultItem,
} from "@/lib/api";

type Props = {
  initialQuery: string;
  initialJobId: number | null;
  initialGraphAware?: boolean;
  initialHideDuplicates?: boolean;
};

type GroupedHit = {
  canonical: SearchResultItem;
  variants: SearchResultItem[];
};

function parseJobId(raw: string | null): number | null {
  if (!raw) return null;
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return null;
  return Math.floor(n);
}

/** Stable display rounding for ranking UI */
const RANK_DECIMALS = 4;

function formatMetric(value: number, decimals: number = RANK_DECIMALS): string {
  if (!Number.isFinite(value)) return "—";
  return value.toFixed(decimals);
}

function formatLatency(ms: number) {
  if (!Number.isFinite(ms)) return "—";
  return `${ms} ms`;
}

/** Lighter info control — full explanations live in fewer panels. */
function InfoTip({ label, children }: { label: string; children: ReactNode }) {
  return (
    <span className="group relative ms-1 inline-flex align-middle">
      <button
        type="button"
        onClick={(e) => {
          e.preventDefault();
          e.stopPropagation();
        }}
        className="inline-flex h-4 w-4 shrink-0 items-center justify-center rounded-full border border-rule/70 bg-paper/80 text-[9px] font-semibold leading-none text-muted/90 outline-none transition-colors hover:border-accent/50 hover:text-accent focus-visible:ring-2 focus-visible:ring-accent"
        aria-label={label}
      >
        i
      </button>
      <span
        role="tooltip"
        className="pointer-events-none invisible absolute left-1/2 top-full z-[60] mt-1.5 w-[min(22rem,calc(100vw-2rem))] -translate-x-1/2 rounded-lg border border-rule bg-paper p-3 text-left text-[11px] font-sans font-normal normal-case leading-snug text-ink opacity-0 shadow-lg ring-1 ring-black/5 transition-all duration-150 group-hover:pointer-events-auto group-hover:visible group-hover:opacity-100 group-focus-within:pointer-events-auto group-focus-within:visible group-focus-within:opacity-100 dark:ring-white/10 sm:left-0 sm:w-[22rem] sm:translate-x-0"
      >
        <span className="pointer-events-auto block max-h-[min(70vh,22rem)] overflow-y-auto pr-0.5">{children}</span>
      </span>
    </span>
  );
}

/** Single help panel for the Search options drawer. */
const HELP_ALL_SEARCH_OPTIONS = (
  <>
    <p className="font-medium text-ink">Search options</p>
    <p className="mt-2 text-muted">
      <strong className="text-ink">Job ID</strong> — Each crawl is its own index and graph. Graph rerank, related
      pages, and duplicate grouping only run when a job is selected (find ids on{" "}
      <span className="font-mono text-ink">/jobs</span>).
    </p>
    <p className="mt-2 text-muted">
      <strong className="text-ink">Graph rerank &amp; related</strong> — Reranks with BM25 + PageRank + neighbor
      boost − duplicate penalty, and loads neighbors from <span className="font-mono text-ink">page_graph_edges</span>{" "}
      under each hit (capped by Related cap).
    </p>
    <p className="mt-2 text-muted">
      <strong className="text-ink">Hide duplicate hits</strong> — Collapses UI cards for hits that are{" "}
      <span className="font-mono text-ink">near_duplicate</span> of an earlier result; does not change server rank
      order.
    </p>
    <p className="mt-2 text-muted">
      <strong className="text-ink">Default</strong> — Leave the drawer closed for plain BM25 (per job if set, else
      global).
    </p>
  </>
);

/** Nested glossary inside “Why this result?” for graph-enhanced rows. */
const HELP_RANKING_GLOSSARY = (
  <div className="space-y-2 text-muted">
    <p>
      <strong className="text-ink">BM25 (norm / raw)</strong> — Norm scales raw BM25 to [0,1] by min–max over the{" "}
      <em>rerank candidate set</em> (top BM25 hits plus graph neighbors), so it can mix with other signals. Raw is the
      same BM25 score as plain search.
    </p>
    <p>
      <strong className="text-ink">PageRank (norm)</strong> — From <span className="font-mono text-ink">page_graph_metrics</span>{" "}
      when present, normalized across candidates. Central pages in the crawl graph score higher.
    </p>
    <p>
      <strong className="text-ink">Neighbor boost</strong> — How strongly this page connects (any edge type) to the top
      BM25 seed pages for your query. “Close to what already matched well.”
    </p>
    <p>
      <strong className="text-ink">Duplicate penalty</strong> — Near-duplicate pressure vs other strong candidates;
      subtracted in the final blend so clusters don’t dominate.
    </p>
    <p>
      <strong className="text-ink">Final</strong> — Weighted sum of normalized BM25 + PR + neighbors − duplicate term;
      used to sort when graph mode is on.
    </p>
    <p className="border-t border-rule/60 pt-2 text-[10px] text-muted">
      <span className="font-mono text-ink">0.0000</span> on normalized columns often means no data or no spread across
      candidates—not an error.
    </p>
  </div>
);

function prettifyScoreExplanation(ex: string) {
  const trimmed = ex.trim();
  const main = trimmed.match(/^final=([\d.]+)\s*=\s*(.+)$/);
  if (!main) {
    return (
      <pre className="mt-1 whitespace-pre-wrap break-words rounded border border-rule/60 bg-paper/50 p-2 font-mono text-[11px] leading-relaxed text-ink">
        {trimmed}
      </pre>
    );
  }
  const finalVal = main[1];
  let rhs = main[2].trim();
  let rawNote: string | null = null;
  const rawM = rhs.match(/\s*\[raw BM25\s+([^\]]+)\]\s*$/);
  if (rawM) {
    rhs = rhs.slice(0, rawM.index).trim();
    rawNote = rawM[0].trim();
  }
  const broken = rhs
    .replace(/\s+\+\s+/g, "\n+ ")
    .replace(/\s+\u2212\s+/g, "\n− ")
    .replace(/\s+-\s+/g, "\n− ");
  const lines = broken.split("\n").map((l) => l.trim());

  return (
    <div className="mt-1.5 rounded border border-rule/60 bg-paper/50 p-2 font-mono text-[11px] leading-relaxed text-ink">
      <div>
        <span className="text-muted">final</span> <span className="text-accent">= {finalVal}</span>
      </div>
      <div className="mt-1 border-l-2 border-accent/40 pl-2">
        <div className="text-muted">=</div>
        {lines.map((line, i) => (
          <div key={i} className="mt-0.5 whitespace-pre-wrap break-all pl-1">
            {line}
          </div>
        ))}
      </div>
      {rawNote ? <div className="mt-2 border-t border-rule/60 pt-2 text-[10px] text-muted">{rawNote}</div> : null}
    </div>
  );
}

function groupForDuplicateCollapse(items: SearchResultItem[], hideDup: boolean): GroupedHit[] {
  if (!hideDup) {
    return items.map((canonical) => ({ canonical, variants: [] as SearchResultItem[] }));
  }
  const byCanonical = new Map<number, SearchResultItem[]>();
  for (const item of items) {
    if (item.is_duplicate_variant && item.canonical_page_id != null) {
      const arr = byCanonical.get(item.canonical_page_id) ?? [];
      arr.push(item);
      byCanonical.set(item.canonical_page_id, arr);
    }
  }
  return items
    .filter((i) => !i.is_duplicate_variant)
    .map((canonical) => ({
      canonical,
      variants: byCanonical.get(canonical.page_id) ?? [],
    }));
}

function TermPill({ term }: { term: string }) {
  return (
    <span className="inline-flex items-center rounded-full border border-rule bg-paper px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest text-muted">
      {term}
    </span>
  );
}

function fallbackRelatedReason(edgeType: string, strength: number): string {
  const et = edgeType.trim() || "unknown";
  const w = Number.isFinite(strength) ? strength : Number.NaN;
  const s = Number.isFinite(w) ? String(w) : "unknown";
  return `Related by ${et} with strength ${s}.`;
}

function RelatedBlock({ related }: { related: RelatedPageRead[] }) {
  if (related.length === 0) return null;
  return (
    <details className="mt-3 border-t border-rule/80 pt-3 [&_summary]:list-none">
      <summary className="cursor-pointer font-mono text-[9px] uppercase tracking-[0.18em] text-muted hover:text-ink">
        Related pages ({related.length})
      </summary>
      <ul className="mt-2 space-y-1.5">
        {related.map((rel) => {
          const isDupEdge = rel.edge_type === "near_duplicate";
          const reasonText = rel.reason?.trim() || fallbackRelatedReason(rel.edge_type, rel.strength);
          const also = rel.also_related_by?.filter(Boolean) ?? [];
          return (
            <li
              key={rel.page_id}
              className={[
                "flex flex-col gap-0.5 rounded border px-2 py-1.5",
                isDupEdge ? "border-dashed border-rule/60 bg-paper/50 opacity-80" : "border-rule/80 bg-paper",
              ].join(" ")}
            >
              <div className="flex min-w-0 flex-wrap items-center gap-2">
                <a
                  href={rel.url}
                  target="_blank"
                  rel="noreferrer"
                  className="min-w-0 flex-1 truncate text-xs font-medium text-accent underline decoration-rule underline-offset-2 hover:decoration-accent"
                  title={rel.url}
                >
                  {rel.title ?? "Untitled page"}
                </a>
                {isDupEdge ? (
                  <span className="shrink-0 rounded border border-amber-500/30 bg-amber-500/10 px-1.5 py-0 font-mono text-[9px] uppercase tracking-wider text-amber-800 dark:text-amber-200">
                    Duplicate
                  </span>
                ) : null}
                <span className="shrink-0 font-mono text-[9px] uppercase tracking-wider text-rule">
                  {rel.edge_type.replace(/_/g, " ")}
                </span>
                <span className="shrink-0 font-mono text-[9px] text-ink">{formatMetric(rel.strength)}</span>
              </div>
              <p className="text-[11px] leading-snug text-muted">{reasonText}</p>
              {also.length > 0 ? (
                <p className="text-[10px] leading-snug text-rule">
                  <span className="font-medium text-ink">Also related by</span> {also.join(", ")}.
                </p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </details>
  );
}

function ScoreBlock({ item }: { item: SearchResultItem }) {
  if (item.score_components) {
    return (
      <div className="flex shrink-0 flex-col items-end gap-0.5 font-mono text-xs text-muted">
        <div className="flex items-baseline gap-2">
          <span className="uppercase tracking-widest">BM25</span>
          <span className="text-ink">{formatMetric(item.score_components.bm25_raw)}</span>
        </div>
        <div className="flex items-baseline gap-2">
          <span className="uppercase tracking-widest">Final</span>
          <span className="text-ink">{formatMetric(item.score)}</span>
        </div>
      </div>
    );
  }
  return (
    <div className="flex shrink-0 items-baseline gap-2 font-mono text-xs text-muted">
      <span className="uppercase tracking-widest">BM25</span>
      <span className="text-ink">{formatMetric(item.score)}</span>
    </div>
  );
}

function Bm25OnlyWhy({ item }: { item: SearchResultItem }) {
  return (
    <div className="mt-2 space-y-3 text-muted">
      <dl className="grid grid-cols-[minmax(0,1fr)_auto] gap-x-3 gap-y-1 font-mono text-[11px] sm:grid-cols-[10rem_1fr]">
        <dt className="text-muted">Total BM25</dt>
        <dd className="text-ink">{formatMetric(item.score)}</dd>
      </dl>
      <div>
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted">Matched query terms</p>
        {item.matched_terms.length > 0 ? (
          <ul className="mt-1 list-inside list-disc font-mono text-[11px] text-ink">
            {item.matched_terms.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-1 text-[11px] text-muted">No indexed query terms matched this page.</p>
        )}
      </div>
      <div>
        <p className="font-mono text-[10px] uppercase tracking-widest text-muted">Snippet (match context)</p>
        <p className="mt-1 text-[11px] leading-relaxed text-ink">{item.snippet?.trim() ? item.snippet : "—"}</p>
      </div>
    </div>
  );
}

function GraphEnhancedWhy({
  sc,
  finalScore,
  explanation,
}: {
  sc: GraphScoreComponentsRead;
  finalScore: number;
  explanation: string | null | undefined;
}) {
  const pr = formatMetric(sc.pagerank_norm);
  const nbN = formatMetric(sc.neighbor_boost_norm);
  const nbR = formatMetric(sc.neighbor_boost_raw);
  const dupN = formatMetric(sc.duplicate_penalty_norm);
  const dupR = formatMetric(sc.duplicate_penalty_raw);
  const bm25N = formatMetric(sc.bm25_norm);
  const bm25R = formatMetric(sc.bm25_raw);
  const finalS = formatMetric(Number.isFinite(finalScore) ? finalScore : sc.final_score);

  return (
    <div className="mt-2 space-y-3 text-muted">
      <dl className="grid grid-cols-1 gap-x-3 gap-y-1.5 font-mono text-[11px] sm:grid-cols-[minmax(0,11rem)_1fr]">
        <dt className="text-muted">BM25 (norm)</dt>
        <dd className="text-ink">{bm25N}</dd>
        <dt className="text-muted">BM25 (raw)</dt>
        <dd className="text-ink">{bm25R}</dd>
        <dt className="text-muted">PageRank (norm)</dt>
        <dd className="text-ink">{pr}</dd>
        <dt className="text-muted">Neighbor boost</dt>
        <dd className="text-ink">
          norm {nbN} · raw {nbR}
        </dd>
        <dt className="text-muted">Duplicate penalty</dt>
        <dd className="text-ink">
          norm {dupN} · raw {dupR}
        </dd>
        <dt className="font-medium text-ink">Final</dt>
        <dd className="font-medium text-ink">{finalS}</dd>
      </dl>
      <details className="rounded-md border border-rule/60 bg-paper/40 text-[11px] [&_summary]:list-none">
        <summary className="cursor-pointer px-2 py-1.5 font-medium text-ink hover:bg-paper/60">
          What these numbers mean
        </summary>
        <div className="border-t border-rule/50 px-2 pb-2 pt-1.5">{HELP_RANKING_GLOSSARY}</div>
      </details>
      {explanation ? (
        <div>
          <p className="font-mono text-[10px] uppercase tracking-widest text-muted">Score formula</p>
          {prettifyScoreExplanation(explanation)}
        </div>
      ) : null}
    </div>
  );
}

function WhyThisResult({ item }: { item: SearchResultItem }) {
  const graph = item.score_components;
  return (
    <details className="mt-3 rounded-lg border border-rule/70 bg-paper/50 px-3 py-2 text-xs text-muted">
      <summary className="cursor-pointer list-none font-mono text-[10px] uppercase tracking-widest text-muted [&::-webkit-details-marker]:hidden">
        Why this result?
      </summary>
      {graph ? (
        <GraphEnhancedWhy sc={graph} finalScore={item.score} explanation={item.score_explanation} />
      ) : (
        <Bm25OnlyWhy item={item} />
      )}
    </details>
  );
}

function ResultCard({
  item,
  variants,
}: {
  item: SearchResultItem;
  variants?: SearchResultItem[];
}) {
  const [dupOpen, setDupOpen] = useState(false);
  const hasVariants = (variants?.length ?? 0) > 0;

  return (
    <article className="rounded border border-rule bg-paper p-4 shadow-lift transition-colors duration-200 sm:p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h3 className="font-serif text-xl font-medium tracking-tight text-ink">
              {item.title ?? "Untitled page"}
            </h3>
            {item.is_duplicate_variant ? (
              <span className="rounded border border-rule/80 bg-rule/20 px-2 py-0.5 font-mono text-[9px] uppercase tracking-widest text-muted">
                Near-duplicate
              </span>
            ) : null}
          </div>
          <a
            className="mt-1 block max-w-full truncate font-mono text-xs text-accent underline decoration-rule underline-offset-4 hover:decoration-accent"
            href={item.url}
            target="_blank"
            rel="noreferrer"
            title={item.url}
          >
            {item.url}
          </a>
          {item.is_duplicate_variant && item.duplicate_explanation ? (
            <p className="mt-2 text-[11px] leading-relaxed text-muted">{item.duplicate_explanation}</p>
          ) : null}
        </div>
        <ScoreBlock item={item} />
      </div>
      <p className="mt-3 text-sm leading-relaxed text-muted">{item.snippet || "—"}</p>
      {item.matched_terms.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-2">
          {item.matched_terms.map((term) => (
            <TermPill key={term} term={term} />
          ))}
        </div>
      ) : null}
      <WhyThisResult item={item} />
      {(item.related ?? []).length > 0 ? <RelatedBlock related={item.related ?? []} /> : null}
      {hasVariants ? (
        <div className="mt-3 border-t border-rule/80 pt-3">
          <button
            type="button"
            onClick={() => setDupOpen((o) => !o)}
            className="flex w-full items-center justify-between rounded border border-dashed border-rule/70 bg-paper px-3 py-2 text-left text-xs text-muted transition-colors hover:border-accent/40"
          >
            <span>
              <span className="font-mono text-[10px] uppercase tracking-widest text-muted">Near-duplicate hits</span>
              <span className="ml-2 text-ink">({variants!.length})</span>
            </span>
            <span className="font-mono text-[10px] text-accent">{dupOpen ? "Hide" : "Show"}</span>
          </button>
          {dupOpen ? (
            <ul className="mt-2 space-y-2">
              {variants!.map((v) => (
                <li
                  key={v.page_id}
                  className="rounded border border-dashed border-rule/60 bg-paper/40 px-3 py-2 opacity-90"
                >
                  <a
                    href={v.url}
                    target="_blank"
                    rel="noreferrer"
                    className="font-medium text-accent underline decoration-rule underline-offset-2"
                  >
                    {v.title ?? "Untitled page"}
                  </a>
                  <p className="mt-0.5 truncate font-mono text-[10px] text-muted" title={v.url}>
                    {v.url}
                  </p>
                  {v.duplicate_explanation ? (
                    <p className="mt-1 text-[11px] text-muted">{v.duplicate_explanation}</p>
                  ) : null}
                </li>
              ))}
            </ul>
          ) : null}
        </div>
      ) : null}
    </article>
  );
}

export function SearchClient({
  initialQuery,
  initialJobId,
  initialGraphAware = false,
  initialHideDuplicates = false,
}: Props) {
  const router = useRouter();
  const [query, setQuery] = useState(initialQuery);
  const [jobIdText, setJobIdText] = useState(initialJobId ? String(initialJobId) : "");
  const [graphAware, setGraphAware] = useState(initialGraphAware && Boolean(initialJobId));
  const [hideDuplicates, setHideDuplicates] = useState(initialHideDuplicates && Boolean(initialJobId));
  const [relatedLimit, setRelatedLimit] = useState(3);
  const [searchOptionsOpen, setSearchOptionsOpen] = useState(
    () => Boolean(initialJobId && (initialGraphAware || initialHideDuplicates)),
  );
  const [loading, setLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [data, setData] = useState<SearchResponse | null>(null);
  const [mapOpen, setMapOpen] = useState(false);

  const lastRequestKeyRef = useRef<string>("");

  const jobId = useMemo(() => parseJobId(jobIdText), [jobIdText]);
  const trimmedQuery = useMemo(() => query.trim(), [query]);

  useEffect(() => {
    if (!jobId) {
      setGraphAware(false);
      setHideDuplicates(false);
      setSearchOptionsOpen(false);
    }
  }, [jobId]);

  const requestKey = useMemo(() => {
    const parts = [
      trimmedQuery,
      jobId ? String(jobId) : "",
      jobId && graphAware ? "ga1" : "ga0",
      jobId && graphAware ? String(relatedLimit) : "",
      jobId && hideDuplicates ? "hd1" : "hd0",
    ];
    return parts.join("|");
  }, [trimmedQuery, jobId, graphAware, hideDuplicates, relatedLimit]);

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
      const rl = Math.min(10, Math.max(1, relatedLimit));
      const useGraphAware = Boolean(nextJobId && graphAware);
      const useAnnotate = Boolean(nextJobId && (hideDuplicates || graphAware));
      const response = await searchPages({
        q,
        job_id: nextJobId ?? undefined,
        limit: 20,
        include_related: useGraphAware,
        related_limit: useGraphAware ? rl : undefined,
        graph_enhanced: useGraphAware,
        annotate_duplicate_hits: useAnnotate,
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
    if (nextJobId && graphAware) url.searchParams.set("graph_aware", "1");
    else url.searchParams.delete("graph_aware");
    if (nextJobId && hideDuplicates) url.searchParams.set("hide_dup", "1");
    else url.searchParams.delete("hide_dup");
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

  const groupedResults = useMemo(() => {
    if (!data?.results.length) return [];
    return groupForDuplicateCollapse(data.results, Boolean(jobId && hideDuplicates));
  }, [data, jobId, hideDuplicates]);

  const headerMeta = useMemo(() => {
    if (!data) return null;
    const hiddenDupes =
      jobId && hideDuplicates ? data.results.filter((r) => Boolean(r.is_duplicate_variant)).length : 0;
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
        {hiddenDupes > 0 ? (
          <>
            <span className="px-2 text-rule">·</span>
            <span>
              <span className="text-ink">{hiddenDupes}</span> near-duplicate{hiddenDupes === 1 ? "" : "s"} collapsed
            </span>
          </>
        ) : null}
      </p>
    );
  }, [data, jobId, hideDuplicates]);

  useEffect(() => {
    if (!data) setMapOpen(false);
  }, [data]);

  return (
    <section className="mt-8 space-y-6">
      <form
        onSubmit={onSubmit}
        className="rounded-xl border border-rule bg-paper p-4 shadow-lift sm:p-5"
      >
        <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:gap-5">
          <div className="min-w-0 flex-1">
            <label className="block text-xs font-medium uppercase tracking-wider text-muted" htmlFor="query">
              Query
            </label>
            <input
              id="query"
              name="query"
              type="text"
              placeholder="fastapi async"
              className="mt-1.5 h-10 w-full rounded-lg border border-rule bg-paper px-3 text-sm text-ink outline-none transition-colors focus:border-accent"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              required
            />
          </div>
          <div className="sm:w-32 sm:shrink-0">
            <label className="block text-xs font-medium uppercase tracking-wider text-muted" htmlFor="job-id">
              Job id <span className="font-normal normal-case tracking-normal">(optional)</span>
            </label>
            <input
              id="job-id"
              name="job-id"
              type="text"
              inputMode="numeric"
              placeholder="e.g. 5"
              className="mt-1.5 h-10 w-full rounded-lg border border-rule bg-paper px-3 font-mono text-sm tabular-nums text-ink outline-none transition-colors focus:border-accent"
              value={jobIdText}
              onChange={(e) => setJobIdText(e.target.value)}
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="h-10 shrink-0 rounded-lg bg-accent px-5 text-sm font-medium text-paper transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:bg-rule"
          >
            {loading ? "Searching…" : "Search"}
          </button>
        </div>
        <p className="mt-3 text-[11px] leading-relaxed text-muted">
          Default: BM25 only. Graph rerank &amp; related pages need a{" "}
          <Link
            href="/jobs"
            className="text-accent underline decoration-rule underline-offset-2 hover:decoration-accent"
          >
            job id
          </Link>
          .
        </p>

        <details
          className="group/details mt-4 rounded-lg border border-rule/50 [&_summary::-webkit-details-marker]:hidden"
          open={searchOptionsOpen}
          onToggle={(e) => setSearchOptionsOpen(e.currentTarget.open)}
        >
          <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs text-muted transition-colors hover:text-ink">
            <span className="select-none">Search options</span>
            {jobId && graphAware ? (
              <span className="rounded bg-accent/15 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-accent">
                Graph
              </span>
            ) : null}
            {jobId && hideDuplicates ? (
              <span className="rounded bg-rule/40 px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-wider text-muted">
                Dedupe
              </span>
            ) : null}
            <span className="ms-auto text-muted transition-transform group-open/details:rotate-180">▾</span>
          </summary>
          <div className="space-y-3 border-t border-rule/50 px-3 pb-3 pt-3">
            <div className="flex justify-end">
              <span className="inline-flex items-center text-[11px] text-muted">
                How these work
                <InfoTip label="Search options explained">{HELP_ALL_SEARCH_OPTIONS}</InfoTip>
              </span>
            </div>
            <label className="flex cursor-pointer items-start gap-3 rounded-md border border-transparent px-1 py-0.5 hover:border-rule/50 hover:bg-paper/50">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-rule text-accent focus:ring-accent"
                checked={graphAware && Boolean(jobId)}
                disabled={!jobId}
                onChange={(e) => setGraphAware(e.target.checked)}
              />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-ink">Graph rerank &amp; related pages</span>
                <span className="mt-0.5 block text-[11px] leading-snug text-muted">
                  BM25 + PageRank + neighbors − duplicate penalty; neighbors listed under each result.
                </span>
                {!jobId ? <span className="mt-1 block text-[11px] text-rule">Requires job id.</span> : null}
              </span>
            </label>
            {jobId && graphAware ? (
              <label className="flex flex-wrap items-center gap-2 pl-7 text-[11px] text-muted">
                <span className="font-mono uppercase tracking-widest">Neighbors per result</span>
                <input
                  type="number"
                  min={1}
                  max={10}
                  className="w-14 rounded-md border border-rule bg-paper px-2 py-1 text-xs text-ink"
                  value={relatedLimit}
                  onChange={(e) => {
                    const n = Number(e.target.value);
                    if (!Number.isFinite(n)) return;
                    setRelatedLimit(Math.min(10, Math.max(1, Math.floor(n))));
                  }}
                />
              </label>
            ) : null}
            <label className="flex cursor-pointer items-start gap-3 rounded-md border border-transparent px-1 py-0.5 hover:border-rule/50 hover:bg-paper/50">
              <input
                type="checkbox"
                className="mt-0.5 h-4 w-4 shrink-0 rounded border-rule text-accent focus:ring-accent"
                checked={hideDuplicates && Boolean(jobId)}
                disabled={!jobId}
                onChange={(e) => setHideDuplicates(e.target.checked)}
              />
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-ink">Collapse near-duplicate hits</span>
                <span className="mt-0.5 block text-[11px] leading-snug text-muted">
                  Group pages that are near-duplicates of an earlier hit under that hit (UI only).
                </span>
                {!jobId ? <span className="mt-1 block text-[11px] text-rule">Requires job id.</span> : null}
              </span>
            </label>
          </div>
        </details>
      </form>

      {headerMeta}

      {data?.query.trim() ? (
        <div className="flex flex-wrap items-center gap-2">
          <button
            type="button"
            onClick={() => setMapOpen(true)}
            className="rounded-lg border border-rule bg-paper px-3 py-1.5 font-mono text-[11px] uppercase tracking-wider text-ink shadow-sm transition-colors hover:border-accent hover:text-accent"
          >
            Open relationship map
          </button>
        </div>
      ) : null}

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
          {groupedResults.map(({ canonical, variants }) => (
            <ResultCard key={canonical.page_id} item={canonical} variants={variants} />
          ))}
        </section>
      ) : null}

      <RelationshipMapModal
        open={mapOpen}
        onClose={() => setMapOpen(false)}
        q={data?.query ?? ""}
        jobId={jobId}
      />
    </section>
  );
}
