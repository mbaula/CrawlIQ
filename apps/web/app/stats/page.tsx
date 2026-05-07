import type { Metadata } from "next";

import { EmptyState } from "@/components/EmptyState";
import { getStats } from "@/lib/api";

export const metadata: Metadata = {
  title: "Stats",
};

function MetricCard({ label, value }: { label: string; value: string }) {
  return (
    <section className="rounded border border-rule bg-paper p-5 shadow-lift transition-colors duration-200">
      <p className="font-mono text-[11px] uppercase tracking-widest text-muted">{label}</p>
      <p className="mt-2 font-serif text-3xl font-semibold tracking-tight text-ink">{value}</p>
    </section>
  );
}

function formatNumber(n: number) {
  return new Intl.NumberFormat().format(n);
}

function formatLatency(avg: number) {
  if (!Number.isFinite(avg)) return "—";
  return `${avg.toFixed(1)} ms`;
}

export default async function StatsPage() {
  let stats: Awaited<ReturnType<typeof getStats>> | null = null;
  let loadError: string | null = null;
  try {
    stats = await getStats();
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Failed to load stats.";
  }

  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Stats</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        System overview: crawl volume, indexing progress, failures, and recent search usage.
      </p>

      {loadError ? (
        <section className="mt-8 rounded border border-danger/40 bg-danger/10 p-4 text-sm text-ink">
          <p className="font-medium">Couldn’t load stats</p>
          <p className="mt-1 text-xs text-muted">{loadError}</p>
        </section>
      ) : null}

      {!stats && !loadError ? (
        <EmptyState title="No stats available" description="Start a crawl and run a few searches to populate stats." />
      ) : null}

      {stats ? (
        <section className="mt-8 space-y-8">
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Total jobs" value={formatNumber(stats.total_crawl_jobs)} />
            <MetricCard label="Pages crawled" value={formatNumber(stats.total_pages_crawled)} />
            <MetricCard label="Pages indexed" value={formatNumber(stats.total_pages_indexed)} />
            <MetricCard label="Failures" value={formatNumber(stats.total_failures)} />
          </section>

          <section className="grid gap-4 sm:grid-cols-2">
            <MetricCard label="Failed URLs (distinct)" value={formatNumber(stats.failed_url_count)} />
            <MetricCard label="Avg search latency" value={formatLatency(stats.average_search_latency_ms)} />
          </section>

          <section className="grid gap-6 lg:grid-cols-2">
            <section className="space-y-3">
              <div className="flex items-end justify-between gap-4">
                <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Recent searches</h2>
                <p className="font-mono text-[11px] uppercase tracking-widest text-muted">
                  {stats.recent_searches.length} rows
                </p>
              </div>
              {stats.recent_searches.length === 0 ? (
                <EmptyState title="No searches logged" description="Run a few searches to populate this table." />
              ) : (
                <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-sm">
                      <thead className="bg-rule/20">
                        <tr className="text-muted">
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Query</th>
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Results</th>
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Latency</th>
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">When</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.recent_searches.map((row) => (
                          <tr key={`${row.created_at}-${row.query}`} className="border-t border-rule/60">
                            <td className="px-4 py-3 text-ink">
                              <span className="block max-w-[36ch] truncate" title={row.query}>
                                {row.query}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.result_count}</td>
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.latency_ms} ms</td>
                            <td className="px-4 py-3 font-mono text-xs text-muted">
                              {new Date(row.created_at).toLocaleString()}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </section>

            <section className="space-y-3">
              <div className="flex items-end justify-between gap-4">
                <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Top domains</h2>
                <p className="font-mono text-[11px] uppercase tracking-widest text-muted">
                  {stats.top_crawled_domains.length} rows
                </p>
              </div>
              {stats.top_crawled_domains.length === 0 ? (
                <EmptyState title="No domains yet" description="Domains appear after pages are indexed." />
              ) : (
                <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-sm">
                      <thead className="bg-rule/20">
                        <tr className="text-muted">
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Domain</th>
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Indexed pages</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.top_crawled_domains.map((row) => (
                          <tr key={row.domain} className="border-t border-rule/60">
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.domain}</td>
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.page_count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </section>
          </section>
        </section>
      ) : null}
    </article>
  );
}
