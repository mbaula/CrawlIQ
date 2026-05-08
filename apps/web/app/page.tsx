import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";
import { getStats, listCrawlJobs, type CrawlJobRead, type CrawlStatsRead } from "@/lib/api";

export const metadata: Metadata = {
  title: "CrawlIQ — Web Crawler & Search",
};

function MetricCard({ label, value, href }: { label: string; value: string; href?: string }) {
  const content = (
    <section className="rounded border border-rule bg-paper p-4 shadow-lift transition-colors duration-200 hover:border-accent/50">
      <p className="font-mono text-[10px] uppercase tracking-widest text-muted">{label}</p>
      <p className="mt-1 font-serif text-2xl font-semibold tracking-tight text-ink">{value}</p>
    </section>
  );
  if (href) {
    return <Link href={href}>{content}</Link>;
  }
  return content;
}

function StatusBadge({ status }: { status: CrawlJobRead["status"] }) {
  const styles: Record<string, string> = {
    queued: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    pending: "border-amber-500/30 bg-amber-500/10 text-amber-700 dark:text-amber-300",
    running: "border-sky-500/30 bg-sky-500/10 text-sky-700 dark:text-sky-300",
    completed: "border-emerald-500/30 bg-emerald-500/10 text-emerald-700 dark:text-emerald-300",
    failed: "border-danger/40 bg-danger/10 text-danger",
    cancelled: "border-rule/70 bg-rule/30 text-muted",
  };
  return (
    <span
      className={[
        "inline-flex items-center rounded-full border px-2 py-0.5 font-mono text-[10px] uppercase tracking-widest",
        styles[status] ?? "border-rule/70 bg-rule/30 text-muted",
      ].join(" ")}
    >
      {status}
    </span>
  );
}

function formatNumber(n: number) {
  return new Intl.NumberFormat().format(n);
}

function formatTime(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default async function HomePage() {
  let stats: CrawlStatsRead | null = null;
  let recentJobs: CrawlJobRead[] = [];
  let loadError: string | null = null;

  try {
    [stats, recentJobs] = await Promise.all([getStats(), listCrawlJobs({ limit: 5, offset: 0 }).then((r) => r.items)]);
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Failed to load dashboard data.";
  }

  return (
    <article className="space-y-10">
      <header>
        <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Dashboard</h1>
        <p className="mt-2 max-w-measure text-sm leading-relaxed text-muted">
          Crawl the web, extract content, build a searchable index. Start a new crawl or explore existing data.
        </p>
      </header>

      {loadError ? (
        <section className="rounded border border-danger/40 bg-danger/10 p-4 text-sm text-ink">
          <p className="font-medium">Couldn't load dashboard</p>
          <p className="mt-1 text-xs text-muted">{loadError}</p>
        </section>
      ) : null}

      {stats ? (
        <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <MetricCard label="Crawl jobs" value={formatNumber(stats.total_crawl_jobs)} href="/jobs" />
          <MetricCard label="Pages crawled" value={formatNumber(stats.total_pages_crawled)} />
          <MetricCard label="Pages indexed" value={formatNumber(stats.total_pages_indexed)} href="/search" />
          <MetricCard label="Failures" value={formatNumber(stats.total_failures)} />
        </section>
      ) : null}

      <section className="grid gap-6 lg:grid-cols-2">
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Quick actions</h2>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <Link
              href="/crawl"
              className="flex flex-col gap-1 rounded border border-accent/30 bg-accent/5 p-4 transition-colors hover:border-accent hover:bg-accent/10"
            >
              <span className="font-medium text-ink">New crawl</span>
              <span className="text-xs text-muted">Start a bounded crawl from a seed URL</span>
            </Link>
            <Link
              href="/search"
              className="flex flex-col gap-1 rounded border border-rule bg-paper p-4 shadow-lift transition-colors hover:border-accent/50"
            >
              <span className="font-medium text-ink">Search index</span>
              <span className="text-xs text-muted">Query indexed pages with full-text search</span>
            </Link>
            <Link
              href="/jobs"
              className="flex flex-col gap-1 rounded border border-rule bg-paper p-4 shadow-lift transition-colors hover:border-accent/50"
            >
              <span className="font-medium text-ink">View jobs</span>
              <span className="text-xs text-muted">Monitor crawl progress and history</span>
            </Link>
            <Link
              href="/stats"
              className="flex flex-col gap-1 rounded border border-rule bg-paper p-4 shadow-lift transition-colors hover:border-accent/50"
            >
              <span className="font-medium text-ink">System stats</span>
              <span className="text-xs text-muted">Volume, latency, and top domains</span>
            </Link>
          </div>
        </section>

        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Recent jobs</h2>
            <Link href="/jobs" className="text-xs text-accent hover:underline">
              View all
            </Link>
          </div>
          {recentJobs.length === 0 && !loadError ? (
            <EmptyState title="No jobs yet" description="Create your first crawl to get started." />
          ) : null}
          {recentJobs.length > 0 ? (
            <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
              <div className="overflow-x-auto">
                <table className="min-w-full border-collapse text-left text-sm">
                  <thead className="bg-rule/20">
                    <tr className="text-muted">
                      <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-widest">Seed</th>
                      <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-widest">Status</th>
                      <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-widest">Pages</th>
                      <th className="px-3 py-2 font-mono text-[10px] uppercase tracking-widest">Created</th>
                    </tr>
                  </thead>
                  <tbody>
                    {recentJobs.map((job) => (
                      <tr key={job.id} className="border-t border-rule/60">
                        <td className="px-3 py-2 text-ink">
                          <Link
                            className="block max-w-[20ch] truncate text-accent underline decoration-rule underline-offset-4 hover:decoration-accent"
                            href={`/jobs/${job.id}`}
                            title={job.seed_url}
                          >
                            {job.seed_url.replace(/^https?:\/\//, "")}
                          </Link>
                        </td>
                        <td className="px-3 py-2">
                          <StatusBadge status={job.status} />
                        </td>
                        <td className="px-3 py-2 font-mono text-xs text-ink">{job.pages_crawled}</td>
                        <td className="px-3 py-2 text-xs text-muted">{formatTime(job.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}
        </section>
      </section>
    </article>
  );
}
