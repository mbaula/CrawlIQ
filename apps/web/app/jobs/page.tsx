import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";
import { listCrawlJobs, type CrawlJobRead } from "@/lib/api";

export const metadata: Metadata = {
  title: "Jobs",
};

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

function formatTime(iso: string) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return iso;
  return new Intl.DateTimeFormat(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(date);
}

export default async function JobsPage() {
  let jobs: CrawlJobRead[] = [];
  let loadError: string | null = null;
  try {
    jobs = await listCrawlJobs({ limit: 100, offset: 0 });
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Failed to load jobs.";
  }

  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Jobs</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Crawl jobs: status, progress counters, timestamps, and links to detail pages.
      </p>

      {loadError ? (
        <section className="mt-8 rounded border border-danger/40 bg-danger/10 p-4 text-sm text-ink">
          <p className="font-medium">Couldn’t load jobs</p>
          <p className="mt-1 text-xs text-muted">{loadError}</p>
        </section>
      ) : null}

      {jobs.length === 0 && !loadError ? (
        <EmptyState
          title="No jobs recorded"
          description="Create a crawl from /crawl. Once workers start crawling and indexing, jobs will appear here."
        />
      ) : null}

      {jobs.length > 0 ? (
        <section className="mt-8 overflow-hidden rounded border border-rule bg-paper shadow-lift">
          <div className="overflow-x-auto">
            <table className="min-w-full border-collapse text-left text-sm">
              <thead className="bg-rule/20">
                <tr className="text-muted">
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Job</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Seed</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Status</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Crawled</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Indexed</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Failed</th>
                  <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Created</th>
                </tr>
              </thead>
              <tbody>
                {jobs.map((job) => (
                  <tr key={job.id} className="border-t border-rule/60">
                    <td className="px-4 py-3 font-mono text-xs text-ink">
                      <Link className="text-accent underline decoration-rule underline-offset-4 hover:decoration-accent" href={`/jobs/${job.id}`}>
                        {job.id}
                      </Link>
                    </td>
                    <td className="px-4 py-3 text-ink">
                      <span className="block max-w-[34ch] truncate" title={job.seed_url}>
                        {job.seed_url}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={job.status} />
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-ink">{job.pages_crawled}</td>
                    <td className="px-4 py-3 font-mono text-xs text-ink">{job.pages_indexed}</td>
                    <td className="px-4 py-3 font-mono text-xs text-ink">{job.pages_failed}</td>
                    <td className="px-4 py-3 text-xs text-muted">{formatTime(job.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : null}
    </article>
  );
}
