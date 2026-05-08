import type { Metadata } from "next";

import { EmptyState } from "@/components/EmptyState";
import { getStats } from "@/lib/api";

export const metadata: Metadata = {
  title: "Stats",
};

function MetricCard({ label, value, subtext }: { label: string; value: string; subtext?: string }) {
  return (
    <section className="rounded border border-rule bg-paper p-5 shadow-lift transition-colors duration-200">
      <p className="font-mono text-[11px] uppercase tracking-widest text-muted">{label}</p>
      <p className="mt-2 font-serif text-3xl font-semibold tracking-tight text-ink">{value}</p>
      {subtext && <p className="mt-1 font-mono text-xs text-muted">{subtext}</p>}
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

function formatPercent(rate: number) {
  return `${(rate * 100).toFixed(1)}%`;
}

function formatDuration(seconds: number | null) {
  if (seconds === null || !Number.isFinite(seconds)) return "—";
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return `${mins}m ${secs}s`;
}

function SectionTitle({ title, count }: { title: string; count?: number }) {
  return (
    <div className="flex items-end justify-between gap-4">
      <h2 className="font-serif text-xl font-medium tracking-tight text-ink">{title}</h2>
      {typeof count === "number" && (
        <p className="font-mono text-[11px] uppercase tracking-widest text-muted">{count} rows</p>
      )}
    </div>
  );
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
        Crawler quality, index health, search quality, and system reliability metrics.
      </p>

      {loadError ? (
        <section className="mt-8 rounded border border-danger/40 bg-danger/10 p-4 text-sm text-ink">
          <p className="font-medium">Couldn't load stats</p>
          <p className="mt-1 text-xs text-muted">{loadError}</p>
        </section>
      ) : null}

      {!stats && !loadError ? (
        <EmptyState title="No stats available" description="Start a crawl and run a few searches to populate stats." />
      ) : null}

      {stats ? (
        <section className="mt-8 space-y-8">
          {/* Primary metrics row */}
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Total jobs" value={formatNumber(stats.total_crawl_jobs)} />
            <MetricCard label="Pages crawled" value={formatNumber(stats.total_pages_crawled)} />
            <MetricCard label="Pages indexed" value={formatNumber(stats.total_pages_indexed)} />
            <MetricCard
              label="Index coverage"
              value={formatPercent(stats.index_coverage)}
              subtext={`${formatNumber(stats.total_pages_indexed)} / ${formatNumber(stats.total_pages_crawled)}`}
            />
          </section>

          {/* Crawl quality metrics */}
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard
              label="Crawl success rate"
              value={formatPercent(stats.crawl_success_rate)}
              subtext={`${formatNumber(stats.total_failures)} failures`}
            />
            <MetricCard
              label="Avg pages/job"
              value={stats.avg_pages_per_job.toFixed(1)}
            />
            <MetricCard
              label="Avg crawl duration"
              value={formatDuration(stats.avg_crawl_duration_seconds)}
            />
            <MetricCard
              label="Failed URLs"
              value={formatNumber(stats.failed_url_count)}
              subtext="distinct URLs"
            />
          </section>

          {/* Search quality metrics */}
          <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <MetricCard label="Total searches" value={formatNumber(stats.total_searches)} />
            <MetricCard
              label="Zero-result searches"
              value={formatNumber(stats.zero_result_searches)}
              subtext={formatPercent(stats.zero_result_rate)}
            />
            <MetricCard label="Avg search latency" value={formatLatency(stats.average_search_latency_ms)} />
            <MetricCard label="P95 search latency" value={formatLatency(stats.p95_search_latency_ms)} />
          </section>

          {/* Index Health panel */}
          <section className="rounded border border-rule bg-paper p-6 shadow-lift">
            <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Index Health</h2>
            <div className="mt-4 grid gap-4 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <div className="flex justify-between border-b border-rule/40 py-2">
                <span className="text-muted">Indexed pages</span>
                <span className="font-mono text-ink">
                  {formatNumber(stats.total_pages_indexed)} / {formatNumber(stats.total_pages_crawled)}
                </span>
              </div>
              <div className="flex justify-between border-b border-rule/40 py-2">
                <span className="text-muted">Coverage</span>
                <span className="font-mono text-ink">{formatPercent(stats.index_coverage)}</span>
              </div>
              <div className="flex justify-between border-b border-rule/40 py-2">
                <span className="text-muted">Unique terms</span>
                <span className="font-mono text-ink">{formatNumber(stats.unique_terms)}</span>
              </div>
              <div className="flex justify-between border-b border-rule/40 py-2">
                <span className="text-muted">Total postings</span>
                <span className="font-mono text-ink">{formatNumber(stats.total_postings)}</span>
              </div>
              <div className="flex justify-between border-b border-rule/40 py-2">
                <span className="text-muted">Avg terms/page</span>
                <span className="font-mono text-ink">{stats.avg_terms_per_page.toFixed(0)}</span>
              </div>
              <div className="flex justify-between border-b border-rule/40 py-2">
                <span className="text-muted">Last indexed</span>
                <span className="font-mono text-ink">
                  {stats.last_indexed_at ? new Date(stats.last_indexed_at).toLocaleString() : "—"}
                </span>
              </div>
              {stats.largest_page && (
                <div className="col-span-full flex justify-between border-b border-rule/40 py-2">
                  <span className="text-muted">Largest page</span>
                  <span className="font-mono text-ink">
                    {stats.largest_page.title || stats.largest_page.url} ({formatNumber(stats.largest_page.token_count)} tokens)
                  </span>
                </div>
              )}
            </div>
          </section>

          {/* Tables grid */}
          <section className="grid gap-6 lg:grid-cols-2">
            {/* Recent searches */}
            <section className="space-y-3">
              <SectionTitle title="Recent searches" count={stats.recent_searches.length} />
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
                        </tr>
                      </thead>
                      <tbody>
                        {stats.recent_searches.slice(0, 10).map((row, i) => (
                          <tr key={`${row.created_at}-${row.query}-${i}`} className="border-t border-rule/60">
                            <td className="px-4 py-3 text-ink">
                              <span className="block max-w-[28ch] truncate" title={row.query}>
                                {row.query}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.result_count}</td>
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.latency_ms} ms</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </section>

            {/* Top queries */}
            <section className="space-y-3">
              <SectionTitle title="Top queries" count={stats.top_queries.length} />
              {stats.top_queries.length === 0 ? (
                <EmptyState title="No queries yet" description="Search queries will be aggregated here." />
              ) : (
                <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-sm">
                      <thead className="bg-rule/20">
                        <tr className="text-muted">
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Query</th>
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Count</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.top_queries.map((row) => (
                          <tr key={row.query} className="border-t border-rule/60">
                            <td className="px-4 py-3 text-ink">
                              <span className="block max-w-[32ch] truncate" title={row.query}>
                                {row.query}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </section>

            {/* Top domains */}
            <section className="space-y-3">
              <SectionTitle title="Top domains" count={stats.top_crawled_domains.length} />
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

            {/* HTTP Status distribution */}
            <section className="space-y-3">
              <SectionTitle title="HTTP status distribution" count={stats.http_status_distribution.length} />
              {stats.http_status_distribution.length === 0 ? (
                <EmptyState title="No status codes" description="HTTP status codes appear after pages are fetched." />
              ) : (
                <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-sm">
                      <thead className="bg-rule/20">
                        <tr className="text-muted">
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Status</th>
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Count</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.http_status_distribution.map((row) => (
                          <tr key={row.status_code} className="border-t border-rule/60">
                            <td className="px-4 py-3 font-mono text-xs text-ink">
                              <span
                                className={
                                  row.status_code >= 200 && row.status_code < 300
                                    ? "text-green-600"
                                    : row.status_code >= 300 && row.status_code < 400
                                      ? "text-yellow-600"
                                      : "text-red-600"
                                }
                              >
                                {row.status_code}
                              </span>
                            </td>
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </section>

            {/* Failures by type */}
            <section className="space-y-3">
              <SectionTitle title="Failures by type" count={stats.failures_by_type.length} />
              {stats.failures_by_type.length === 0 ? (
                <EmptyState title="No failures" description="Great! No crawl errors have been recorded." />
              ) : (
                <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-sm">
                      <thead className="bg-rule/20">
                        <tr className="text-muted">
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Error type</th>
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Count</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.failures_by_type.map((row) => (
                          <tr key={row.error_type} className="border-t border-rule/60">
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.error_type}</td>
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.count}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </section>
              )}
            </section>

            {/* Zero-result searches */}
            <section className="space-y-3">
              <SectionTitle title="Recent zero-result searches" count={stats.recent_zero_result_searches.length} />
              {stats.recent_zero_result_searches.length === 0 ? (
                <EmptyState title="No zero-result searches" description="All searches have returned results." />
              ) : (
                <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-sm">
                      <thead className="bg-rule/20">
                        <tr className="text-muted">
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Query</th>
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">When</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.recent_zero_result_searches.map((row, i) => (
                          <tr key={`${row.created_at}-${row.query}-${i}`} className="border-t border-rule/60">
                            <td className="px-4 py-3 text-ink">
                              <span className="block max-w-[28ch] truncate" title={row.query}>
                                {row.query}
                              </span>
                            </td>
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
          </section>

          {/* Recent failed URLs - full width */}
          <section className="space-y-3">
            <SectionTitle title="Recent failed URLs" count={stats.recent_failed_urls.length} />
            {stats.recent_failed_urls.length === 0 ? (
              <EmptyState title="No failed URLs" description="No crawl failures have been recorded." />
            ) : (
              <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                <div className="overflow-x-auto">
                  <table className="min-w-full border-collapse text-left text-sm">
                    <thead className="bg-rule/20">
                      <tr className="text-muted">
                        <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">URL</th>
                        <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Type</th>
                        <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Message</th>
                        <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">When</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stats.recent_failed_urls.map((row, i) => (
                        <tr key={`${row.url}-${row.created_at}-${i}`} className="border-t border-rule/60">
                          <td className="px-4 py-3 text-ink">
                            <a
                              href={row.url}
                              target="_blank"
                              rel="noopener noreferrer"
                              className="block max-w-[40ch] truncate text-accent underline-offset-2 hover:underline"
                              title={row.url}
                            >
                              {row.url}
                            </a>
                          </td>
                          <td className="px-4 py-3 font-mono text-xs text-ink">{row.error_type}</td>
                          <td className="px-4 py-3 text-xs text-muted">
                            <span className="block max-w-[30ch] truncate" title={row.error_message || ""}>
                              {row.error_message || "—"}
                            </span>
                          </td>
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
        </section>
      ) : null}
    </article>
  );
}
