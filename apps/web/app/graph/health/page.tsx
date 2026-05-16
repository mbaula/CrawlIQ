import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";
import {
  fetchGraphHealth,
  listCrawlJobs,
  type GraphHealthClusterRow,
  type GraphHealthDuplicateClusterRead,
  type GraphHealthPageRow,
  type GraphHealthRead,
} from "@/lib/api";

export const metadata: Metadata = {
  title: "Graph health",
};

function firstParam(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) return value[0];
  return value;
}

function parseJobId(raw: string | undefined): number | undefined {
  const n = Number(raw);
  if (!Number.isFinite(n) || n < 1) return undefined;
  return Math.floor(n);
}

function exploreSearchHref(jobId: number, pageId: number): string {
  return `/search?job_id=${jobId}&q=a&map=1&page_id=${pageId}`;
}

function PageTable({
  rows,
  extraCols,
}: {
  rows: GraphHealthPageRow[];
  extraCols: "degrees" | "link_in" | "none";
}) {
  if (rows.length === 0) {
    return <p className="font-mono text-xs text-muted">No rows.</p>;
  }
  return (
    <div className="overflow-x-auto rounded border border-rule">
      <table className="w-full min-w-[32rem] border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-rule bg-paper/80 font-mono uppercase tracking-wider text-muted">
            <th className="px-2 py-2">Page</th>
            <th className="px-2 py-2">URL</th>
            {extraCols === "degrees" ? (
              <>
                <th className="px-2 py-2 text-right">PR</th>
                <th className="px-2 py-2 text-right">In</th>
                <th className="px-2 py-2 text-right">Out</th>
              </>
            ) : null}
            {extraCols === "link_in" ? (
              <th className="px-2 py-2 text-right">Link in</th>
            ) : null}
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.page_id} className="border-b border-rule/60 last:border-b-0">
              <td className="px-2 py-1.5 text-ink">{r.title ?? "—"}</td>
              <td className="max-w-[14rem] truncate px-2 py-1.5 font-mono text-muted" title={r.url}>
                {r.url}
              </td>
              {extraCols === "degrees" ? (
                <>
                  <td className="px-2 py-1.5 text-right font-mono text-ink">
                    {r.pagerank != null ? r.pagerank.toFixed(4) : "—"}
                  </td>
                  <td className="px-2 py-1.5 text-right font-mono text-ink">{r.in_degree ?? "—"}</td>
                  <td className="px-2 py-1.5 text-right font-mono text-ink">{r.out_degree ?? "—"}</td>
                </>
              ) : null}
              {extraCols === "link_in" ? (
                <td className="px-2 py-1.5 text-right font-mono text-ink">{r.link_in_count ?? "—"}</td>
              ) : null}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClusterTable({ jobId, rows }: { jobId: number; rows: GraphHealthClusterRow[] }) {
  if (rows.length === 0) return <p className="font-mono text-xs text-muted">No clusters.</p>;
  return (
    <div className="overflow-x-auto rounded border border-rule">
      <table className="w-full min-w-[28rem] border-collapse text-left text-xs">
        <thead>
          <tr className="border-b border-rule bg-paper/80 font-mono uppercase tracking-wider text-muted">
            <th className="px-2 py-2">cluster_id</th>
            <th className="px-2 py-2 text-right">Members</th>
            <th className="px-2 py-2">Representative</th>
            <th className="px-2 py-2">Explore</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr key={r.cluster_id} className="border-b border-rule/60 last:border-b-0">
              <td className="px-2 py-1.5 font-mono text-ink">{r.cluster_id}</td>
              <td className="px-2 py-1.5 text-right font-mono text-ink">{r.member_count}</td>
              <td className="px-2 py-1.5">
                <div className="text-ink">{r.representative_title ?? "—"}</div>
                <div className="truncate font-mono text-[10px] text-muted" title={r.representative_url}>
                  {r.representative_url}
                </div>
                {r.cluster_label ? (
                  <div className="mt-0.5 font-mono text-[10px] text-rule">label: {r.cluster_label}</div>
                ) : null}
                {r.sample_urls.length > 0 ? (
                  <div className="mt-1 font-mono text-[10px] text-muted">
                    samples: {r.sample_urls.slice(0, 3).join(" · ")}
                  </div>
                ) : null}
              </td>
              <td className="px-2 py-1.5 align-top">
                <Link
                  href={exploreSearchHref(jobId, r.representative_page_id)}
                  className="font-mono text-[10px] uppercase tracking-wider text-accent underline decoration-rule underline-offset-2 hover:decoration-accent"
                >
                  Search map
                </Link>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function DuplicateSection({ jobId, rows }: { jobId: number; rows: GraphHealthDuplicateClusterRead[] }) {
  if (rows.length === 0) return <p className="font-mono text-xs text-muted">No near-duplicate canonical hubs.</p>;
  return (
    <ul className="space-y-4">
      {rows.map((c) => (
        <li key={c.canonical_page_id} className="rounded border border-rule bg-paper/50 p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <div>
              <p className="font-medium text-ink">{c.canonical_title ?? "Untitled"}</p>
              <p className="mt-0.5 truncate font-mono text-[10px] text-muted" title={c.canonical_url}>
                {c.canonical_url}
              </p>
            </div>
            <div className="flex shrink-0 flex-col items-end gap-1">
              <span className="font-mono text-[10px] uppercase tracking-wider text-muted">
                {c.duplicate_count} duplicate{c.duplicate_count === 1 ? "" : "s"}
              </span>
              <Link
                href={exploreSearchHref(jobId, c.canonical_page_id)}
                className="font-mono text-[10px] uppercase tracking-wider text-accent underline decoration-rule underline-offset-2 hover:decoration-accent"
              >
                Search map
              </Link>
            </div>
          </div>
          <ul className="mt-2 space-y-1 border-t border-rule/60 pt-2 font-mono text-[10px] text-muted">
            {c.duplicates.map((d) => (
              <li key={d.page_id} className="flex flex-wrap justify-between gap-2">
                <span className="min-w-0 truncate text-ink" title={d.url}>
                  {d.title ?? d.url}
                </span>
                <span className="shrink-0 text-rule">w={d.weight.toFixed(3)}</span>
              </li>
            ))}
          </ul>
        </li>
      ))}
    </ul>
  );
}

type Props = {
  searchParams?: Record<string, string | string[] | undefined>;
};

export default async function GraphHealthPage({ searchParams }: Props) {
  const jobId = parseJobId(firstParam(searchParams?.job_id)?.toString());

  let health: GraphHealthRead | null = null;
  let jobsError: string | null = null;
  let jobs: { id: number; seed_url: string; status: string }[] = [];

  try {
    health = await fetchGraphHealth(jobId != null ? { job_id: jobId } : {});
  } catch (e) {
    jobsError = e instanceof Error ? e.message : "Failed to load graph health.";
  }

  try {
    const res = await listCrawlJobs({ limit: 40, offset: 0 });
    jobs = res.items.map((j) => ({ id: j.id, seed_url: j.seed_url, status: j.status }));
  } catch {
    /* job list optional */
  }

  const s = health?.summary;

  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Graph health</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Read-only summary of precomputed graph metrics, clusters, and edges for a crawl job. No algorithms run in this
        request beyond SQL aggregation.
      </p>

      <form
        method="get"
        action="/graph/health"
        className="mt-6 flex flex-wrap items-end gap-3 rounded border border-rule bg-paper p-4 shadow-lift"
      >
        <label className="flex flex-col gap-1">
          <span className="font-mono text-[11px] uppercase tracking-widest text-muted">Crawl job</span>
          <select
            name="job_id"
            defaultValue={jobId != null ? String(jobId) : ""}
            className="min-w-[12rem] rounded border border-rule bg-paper px-3 py-2 text-sm text-ink"
          >
            <option value="">Select job…</option>
            {jobs.map((j) => (
              <option key={j.id} value={j.id}>
                #{j.id} · {j.status} · {j.seed_url.slice(0, 48)}
                {j.seed_url.length > 48 ? "…" : ""}
              </option>
            ))}
          </select>
        </label>
        <button
          type="submit"
          className="h-10 rounded-lg bg-accent px-4 text-sm font-medium text-paper transition-colors hover:bg-accent/90"
        >
          Load
        </button>
      </form>

      {jobsError ? (
        <section className="mt-6 rounded border border-danger/40 bg-danger/10 p-4 text-sm text-ink">
          <p className="font-medium">Could not load health</p>
          <p className="mt-1 font-mono text-xs text-muted">{jobsError}</p>
        </section>
      ) : null}

      {health && health.job_id == null ? (
        <div className="mt-8">
          <EmptyState title="Pick a crawl job" description={health.message ?? "Choose a job id to see graph health."} />
        </div>
      ) : null}

      {health && health.job_id != null && s ? (
        <div className="mt-8 space-y-10">
          {health.message ? (
            <p className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-sm text-ink">{health.message}</p>
          ) : null}

          <section>
            <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Summary</h2>
            <dl className="mt-2 grid max-w-2xl grid-cols-2 gap-x-4 gap-y-1 font-mono text-xs sm:grid-cols-3">
              <dt className="text-muted">Pages</dt>
              <dd className="text-ink">{s.page_count}</dd>
              <dt className="text-muted">Edges</dt>
              <dd className="text-ink">{s.edge_count}</dd>
              <dt className="text-muted">Metrics rows</dt>
              <dd className="text-ink">{s.metrics_count}</dd>
              <dt className="text-muted">Cluster rows</dt>
              <dd className="text-ink">{s.cluster_row_count}</dd>
              <dt className="text-muted">Distinct cluster ids</dt>
              <dd className="text-ink">{s.distinct_cluster_ids}</dd>
              <dt className="text-muted">Orphans (listed / cap)</dt>
              <dd className="text-ink">{s.orphan_count}</dd>
              <dt className="text-muted">Duplicate hubs</dt>
              <dd className="text-ink">{s.duplicate_cluster_count}</dd>
            </dl>
            {s.orphan_detection_warning ? (
              <p className="mt-3 rounded border border-rule bg-paper/80 p-2 text-[11px] leading-relaxed text-muted">
                {s.orphan_detection_warning}
              </p>
            ) : null}
          </section>

          {s.edge_count === 0 ? (
            <EmptyState
              title="No graph edges yet"
              description="Run graph edge generation for this job, then reload."
            />
          ) : (
            <>
              <section>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">High PageRank</h2>
                <p className="mt-1 text-[11px] text-muted">From page_graph_metrics (precomputed).</p>
                <div className="mt-2">
                  <PageTable rows={health.top_pagerank_pages} extraCols="degrees" />
                </div>
              </section>

              <section>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Hub pages (out-degree)</h2>
                <div className="mt-2">
                  <PageTable rows={health.hub_pages} extraCols="degrees" />
                </div>
              </section>

              <section>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Authority mix</h2>
                <p className="mt-1 text-[11px] text-muted">
                  Merged from high PageRank and high in-degree lists (deduped, bounded).
                </p>
                <div className="mt-2">
                  <PageTable rows={health.authority_pages} extraCols="degrees" />
                </div>
              </section>

              <section>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Most linked (incoming link edges)</h2>
                <div className="mt-2">
                  <PageTable rows={health.most_linked_pages} extraCols="link_in" />
                </div>
              </section>

              <section>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Orphan pages</h2>
                <p className="mt-1 text-[11px] text-muted">
                  in_degree = 0 and out_degree = 0 in metrics when complete coverage; otherwise no incident edges.
                </p>
                <div className="mt-2">
                  <PageTable rows={health.orphan_pages} extraCols="none" />
                </div>
              </section>

              <section>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Largest clusters</h2>
                <p className="mt-1 text-[11px] text-muted">page_graph_clusters grouped by cluster_id (member count).</p>
                <div className="mt-2">
                  <ClusterTable jobId={health.job_id} rows={health.largest_clusters} />
                </div>
              </section>

              <section>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">
                  Small clusters / isolated sections
                </h2>
                <p className="mt-1 text-[11px] text-muted">
                  Low member-count groups from page_graph_clusters (not weakly connected components).
                </p>
                <div className="mt-2">
                  <ClusterTable jobId={health.job_id} rows={health.small_clusters} />
                </div>
              </section>

              <section>
                <h2 className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Duplicate clusters</h2>
                <p className="mt-1 text-[11px] text-muted">
                  Canonical pages with outgoing near_duplicate edges (not page_graph_clusters).
                </p>
                <div className="mt-2">
                  <DuplicateSection jobId={health.job_id} rows={health.duplicate_clusters} />
                </div>
              </section>
            </>
          )}
        </div>
      ) : null}
    </article>
  );
}
