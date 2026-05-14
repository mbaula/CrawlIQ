import type { Metadata } from "next";
import type { ReactNode } from "react";

import { EmptyState } from "@/components/EmptyState";
import { getStats } from "@/lib/api";

export const metadata: Metadata = {
  title: "Stats",
};

function MetricCard({
  label,
  value,
  subtext,
  className = "",
}: {
  label: string;
  value: string;
  subtext?: string;
  className?: string;
}) {
  return (
    <section
      className={`min-w-0 overflow-hidden rounded border border-rule bg-paper p-4 shadow-lift transition-colors duration-200 sm:p-5 ${className}`}
    >
      <p className="font-mono text-[11px] uppercase tracking-widest text-muted">{label}</p>
      <p className="mt-2 break-words font-serif text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{value}</p>
      {subtext && (
        <p className="mt-1 font-mono text-xs leading-snug text-muted [overflow-wrap:anywhere]">{subtext}</p>
      )}
    </section>
  );
}

function StatRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="flex min-w-0 gap-4 border-b border-rule/40 py-2.5 pr-1 sm:pr-2">
      <span className="min-w-0 flex-1 text-muted">{label}</span>
      <span className="shrink-0 text-right font-mono text-sm tabular-nums text-ink sm:text-base">{value}</span>
    </div>
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
        Each URL attempt is either a stored page (fetched) or a crawl error row—never both. “Pages crawled” here means successful fetches, not “attempts.”
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
          {/* Primary pipeline metrics */}
          <section className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            <MetricCard label="URLs attempted" value={formatNumber(stats.total_urls_attempted)} subtext="pages + error rows" />
            <MetricCard label="Pages fetched" value={formatNumber(stats.total_pages_crawled)} subtext="successful stores" />
            <MetricCard label="Pages indexed" value={formatNumber(stats.total_pages_indexed)} />
            <MetricCard label="Fetch success rate" value={formatPercent(stats.crawl_success_rate)} subtext="fetched ÷ attempted" />
            <MetricCard
              label="Index coverage"
              value={formatPercent(stats.index_coverage)}
              subtext={`indexed ÷ fetched`}
            />
            <MetricCard
              label="Skipped URLs"
              value={formatNumber(stats.total_skipped_rows)}
              subtext="robots, MIME, size caps"
            />
            <MetricCard
              label="Failed URLs"
              value={formatNumber(stats.failed_url_count)}
              subtext="distinct URLs with errors"
            />
          </section>

          <section className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            <MetricCard label="Total jobs" value={formatNumber(stats.total_crawl_jobs)} />
            <MetricCard label="Avg pages / job" value={stats.avg_pages_per_job.toFixed(1)} />
            <MetricCard label="Avg crawl duration" value={formatDuration(stats.avg_crawl_duration_seconds)} />
          </section>

          {/* Crawler outcomes */}
          <section className="rounded border border-rule bg-paper p-5 shadow-lift sm:p-6">
            <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Crawler outcomes</h2>
            <p className="mt-1 text-xs text-muted">
              Attempted = every URL tried. Fetched = persisted page. Skipped = policy (no full index). Failed = transport/post-fetch
              errors (excludes robots / MIME / size skips).
            </p>
            <div className="mt-4 grid grid-cols-1 gap-x-6 gap-y-0 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <StatRow label="URLs attempted" value={formatNumber(stats.total_urls_attempted)} />
              <StatRow label="Fetched successfully" value={formatNumber(stats.total_pages_crawled)} />
              <StatRow label="Indexed" value={formatNumber(stats.total_pages_indexed)} />
              <StatRow label="Skipped" value={formatNumber(stats.total_skipped_rows)} />
              <StatRow label="Failed (fetch)" value={formatNumber(stats.fetch_failure_row_count)} />
            </div>
            <p className="mt-3 text-xs text-muted">
              Pending indexing: {formatNumber(stats.pages_pending_indexing)} · Rows in{" "}
              <span className="font-mono">crawl_errors</span>: {formatNumber(stats.total_failures)}
            </p>
          </section>

          {/* Indexing + search distributions */}
          <section className="rounded border border-rule bg-paper p-5 shadow-lift sm:p-6">
            <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Indexing &amp; search</h2>
            <div className="mt-4 grid grid-cols-1 gap-x-6 gap-y-0 text-sm sm:grid-cols-2 xl:grid-cols-3">
              <StatRow label="Median terms / page" value={stats.median_terms_per_page.toFixed(0)} />
              <StatRow label="P95 terms / page" value={stats.p95_terms_per_page.toFixed(0)} />
              <StatRow label="Avg results / search" value={stats.avg_results_per_search.toFixed(1)} />
              <StatRow label="Zero-result rate" value={formatPercent(stats.zero_result_rate)} />
              <StatRow
                label="Avg fetch latency"
                value={stats.avg_fetch_latency_ms != null ? formatLatency(stats.avg_fetch_latency_ms) : "—"}
              />
              <StatRow
                label="P95 fetch latency"
                value={stats.p95_fetch_latency_ms != null ? formatLatency(stats.p95_fetch_latency_ms) : "—"}
              />
              <div className="col-span-full flex min-w-0 flex-col gap-1 border-b border-rule/40 py-2.5 pr-1 sm:pr-2">
                <div className="flex min-w-0 gap-4">
                  <span className="min-w-0 flex-1 text-muted">Slowest search</span>
                  <span className="shrink-0 font-mono text-xs tabular-nums text-ink sm:text-sm">
                    {stats.slowest_search_latency_ms != null ? `${stats.slowest_search_latency_ms} ms` : "—"}
                  </span>
                </div>
                {stats.slowest_search_query ? (
                  <p className="truncate font-mono text-[11px] text-muted" title={stats.slowest_search_query}>
                    {stats.slowest_search_query}
                  </p>
                ) : null}
              </div>
              <StatRow label="Queries at 20+ results" value={formatNumber(stats.searches_hitting_result_cap)} />
            </div>
          </section>

          {/* Search latency cards */}
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

          {/* HTTP status classes + reliability */}
          <section className="grid gap-4 lg:grid-cols-2">
            <section className="rounded border border-rule bg-paper p-5 shadow-lift">
              <h2 className="font-serif text-lg font-medium tracking-tight text-ink">HTTP status distribution</h2>
              <p className="mt-1 text-xs text-muted">
                Combines status from indexed pages with HTTP codes on failed fetches (403, 429, 5xx, etc.).
              </p>
              <div className="mt-3 grid grid-cols-2 gap-2 font-mono text-sm sm:grid-cols-4">
                <div>
                  <span className="text-muted">2xx</span>{" "}
                  <span className="text-ink">{formatNumber(stats.http_status_class_totals.status_2xx)}</span>
                </div>
                <div>
                  <span className="text-muted">3xx</span>{" "}
                  <span className="text-ink">{formatNumber(stats.http_status_class_totals.status_3xx)}</span>
                </div>
                <div>
                  <span className="text-muted">4xx</span>{" "}
                  <span className="text-ink">{formatNumber(stats.http_status_class_totals.status_4xx)}</span>
                </div>
                <div>
                  <span className="text-muted">5xx</span>{" "}
                  <span className="text-ink">{formatNumber(stats.http_status_class_totals.status_5xx)}</span>
                </div>
              </div>
            </section>
            <section className="rounded border border-rule bg-paper p-5 shadow-lift">
              <h2 className="font-serif text-lg font-medium tracking-tight text-ink">Fetch reliability</h2>
              <div className="mt-3 space-y-2 font-mono text-sm">
                <div className="flex justify-between border-b border-rule/40 py-1">
                  <span className="text-muted">HTTP 429 (rate limited)</span>
                  <span className="text-ink">{formatNumber(stats.rate_limited_url_count)}</span>
                </div>
                <div className="flex justify-between border-b border-rule/40 py-1">
                  <span className="text-muted">Timeouts</span>
                  <span className="text-ink">{formatNumber(stats.timeout_fetch_count)}</span>
                </div>
              </div>
            </section>
          </section>

          {/* Index corpus */}
          <section className="rounded border border-rule bg-paper p-5 shadow-lift sm:p-6">
            <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Index corpus</h2>
            <div className="mt-4 grid grid-cols-1 gap-x-6 gap-y-0 text-sm sm:grid-cols-2 lg:grid-cols-3">
              <StatRow label="Unique terms" value={formatNumber(stats.unique_terms)} />
              <StatRow label="Total postings" value={formatNumber(stats.total_postings)} />
              <StatRow label="Avg terms / page" value={stats.avg_terms_per_page.toFixed(0)} />
              <StatRow
                label="Last indexed"
                value={stats.last_indexed_at ? new Date(stats.last_indexed_at).toLocaleString() : "—"}
              />
              {stats.largest_page && (
                <div className="col-span-full flex min-w-0 items-start gap-4 border-b border-rule/40 py-2.5 pr-1 sm:pr-2">
                  <span className="min-w-0 shrink pt-0.5 text-muted">Largest page (tokens)</span>
                  <span className="min-w-0 flex-1 text-right font-mono text-xs leading-snug text-ink [overflow-wrap:anywhere] sm:text-sm">
                    {stats.largest_page.title || stats.largest_page.url} ({formatNumber(stats.largest_page.token_count)})
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

            {/* Top failure domains */}
            <section className="space-y-3 lg:col-span-2">
              <SectionTitle title="Top domains by crawl errors" count={stats.top_failure_domains.length} />
              {stats.top_failure_domains.length === 0 ? (
                <EmptyState title="No crawl errors" description="Domains appear when URLs fail with recorded errors." />
              ) : (
                <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                  <div className="overflow-x-auto">
                    <table className="min-w-full border-collapse text-left text-sm">
                      <thead className="bg-rule/20">
                        <tr className="text-muted">
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Domain</th>
                          <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Errors</th>
                        </tr>
                      </thead>
                      <tbody>
                        {stats.top_failure_domains.map((row) => (
                          <tr key={row.domain} className="border-t border-rule/60">
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.domain}</td>
                            <td className="px-4 py-3 font-mono text-xs text-ink">{row.failure_count}</td>
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
              <SectionTitle title="HTTP codes (detail)" count={stats.http_status_distribution.length} />
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

            {/* Skipped vs fetch failures */}
            <section className="space-y-3 lg:col-span-2">
              <div className="grid gap-6 lg:grid-cols-2">
                <div className="space-y-3">
                  <SectionTitle title="Skipped URLs (policy)" count={stats.skipped_breakdown.length} />
                  <p className="text-xs text-muted">Intentionally not indexed: robots, MIME, size, etc.</p>
                  <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                    <div className="overflow-x-auto">
                      <table className="min-w-full border-collapse text-left text-sm">
                        <thead className="bg-rule/20">
                          <tr className="text-muted">
                            <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Reason</th>
                            <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Count</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stats.skipped_breakdown.map((row) => (
                            <tr key={row.error_type} className="border-t border-rule/60">
                              <td className="px-4 py-3 text-xs text-ink">{row.error_type}</td>
                              <td className="px-4 py-3 font-mono text-xs text-ink">{row.count}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </div>
                <div className="space-y-3">
                  <SectionTitle title="Fetch failures" count={stats.fetch_failures_breakdown.length} />
                  <p className="text-xs text-muted">Transport and HTTP after attempting a fetch; 429 split out.</p>
                  <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
                    <div className="overflow-x-auto">
                      <table className="min-w-full border-collapse text-left text-sm">
                        <thead className="bg-rule/20">
                          <tr className="text-muted">
                            <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Reason</th>
                            <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Count</th>
                          </tr>
                        </thead>
                        <tbody>
                          {stats.fetch_failures_breakdown.map((row) => (
                            <tr key={row.error_type} className="border-t border-rule/60">
                              <td className="px-4 py-3 font-mono text-xs text-ink">{row.error_type}</td>
                              <td className="px-4 py-3 font-mono text-xs text-ink">{row.count}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </section>
                </div>
              </div>
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
