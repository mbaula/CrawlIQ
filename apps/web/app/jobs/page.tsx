import type { Metadata } from "next";
import Link from "next/link";
import { redirect } from "next/navigation";

import { EmptyState } from "@/components/EmptyState";
import { listCrawlJobs, type CrawlJobRead } from "@/lib/api";

export const metadata: Metadata = {
  title: "Jobs",
};

const PAGE_SIZES = [10, 20, 50] as const;
const JOB_STATUSES = ["queued", "pending", "running", "completed", "failed", "cancelled"] as const;

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

function firstString(v: string | string[] | undefined): string | undefined {
  if (v === undefined) return undefined;
  return Array.isArray(v) ? v[0] : v;
}

function parsePage(raw: string | undefined): number {
  const n = parseInt(raw ?? "", 10);
  if (!Number.isFinite(n) || n < 1) return 1;
  return n;
}

function parsePageSize(raw: string | undefined): number {
  const n = parseInt(raw ?? "", 10);
  if ((PAGE_SIZES as readonly number[]).includes(n)) return n;
  return 20;
}

function parseStatus(raw: string | undefined): string | undefined {
  const s = raw?.trim();
  if (!s) return undefined;
  return (JOB_STATUSES as readonly string[]).includes(s) ? s : undefined;
}

function jobsListQueryString(opts: {
  page: number;
  pageSize: number;
  status?: string;
  q?: string;
}): string {
  const p = new URLSearchParams();
  p.set("page", String(opts.page));
  p.set("page_size", String(opts.pageSize));
  if (opts.status) p.set("status", opts.status);
  const q = opts.q?.trim();
  if (q) p.set("q", q);
  return p.toString();
}

type JobsPageProps = {
  searchParams: Record<string, string | string[] | undefined>;
};

export default async function JobsPage({ searchParams }: JobsPageProps) {
  const page = parsePage(firstString(searchParams.page));
  const pageSize = parsePageSize(firstString(searchParams.page_size));
  const statusFilter = parseStatus(firstString(searchParams.status));
  const qRaw = firstString(searchParams.q) ?? "";
  const q = qRaw.slice(0, 500);

  const offset = (page - 1) * pageSize;

  let jobs: CrawlJobRead[] = [];
  let total = 0;
  let loadError: string | null = null;
  try {
    const res = await listCrawlJobs({
      limit: pageSize,
      offset,
      status: statusFilter,
      q: q || undefined,
    });
    jobs = res.items;
    total = res.total;
  } catch (error) {
    loadError = error instanceof Error ? error.message : "Failed to load jobs.";
  }

  const totalPages = Math.max(1, Math.ceil(total / pageSize));
  if (!loadError && total > 0 && page > totalPages) {
    redirect(`/jobs?${jobsListQueryString({ page: totalPages, pageSize, status: statusFilter, q })}`);
  }

  const queryBase = { pageSize, status: statusFilter, q };
  const isFiltered = Boolean(statusFilter || q.trim());

  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Jobs</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Crawl jobs: status, progress counters, timestamps, and links to detail pages.
      </p>

      {!loadError ? (
        <form
          className="mt-6 flex flex-col gap-3 rounded border border-rule bg-paper p-4 shadow-lift sm:flex-row sm:flex-wrap sm:items-end"
          method="get"
          action="/jobs"
        >
          <input type="hidden" name="page" value="1" />
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="font-mono text-[11px] uppercase tracking-widest text-muted">Search seed URL</span>
            <input
              type="search"
              name="q"
              defaultValue={q}
              placeholder="example.com"
              className="rounded border border-rule bg-paper px-3 py-2 text-sm text-ink outline-none ring-accent/30 placeholder:text-muted focus:border-accent focus:ring-2"
              autoComplete="off"
            />
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[11px] uppercase tracking-widest text-muted">Status</span>
            <select
              name="status"
              defaultValue={statusFilter ?? ""}
              className="rounded border border-rule bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
            >
              <option value="">All</option>
              {JOB_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1">
            <span className="font-mono text-[11px] uppercase tracking-widest text-muted">Per page</span>
            <select
              name="page_size"
              defaultValue={String(pageSize)}
              className="rounded border border-rule bg-paper px-3 py-2 text-sm text-ink outline-none focus:border-accent focus:ring-2 focus:ring-accent/30"
            >
              {PAGE_SIZES.map((n) => (
                <option key={n} value={n}>
                  {n}
                </option>
              ))}
            </select>
          </label>
          <div className="flex gap-2">
            <button
              type="submit"
              className="rounded border border-accent bg-accent px-4 py-2 text-sm font-medium text-paper transition-colors hover:opacity-90"
            >
              Apply
            </button>
            {isFiltered ? (
              <Link
                href="/jobs"
                className="rounded border border-rule px-4 py-2 text-sm text-muted transition-colors hover:border-accent hover:text-ink"
              >
                Clear
              </Link>
            ) : null}
          </div>
        </form>
      ) : null}

      {loadError ? (
        <section className="mt-8 rounded border border-danger/40 bg-danger/10 p-4 text-sm text-ink">
          <p className="font-medium">Couldn’t load jobs</p>
          <p className="mt-1 text-xs text-muted">{loadError}</p>
        </section>
      ) : null}

      {!loadError && total === 0 ? (
        <EmptyState
          title={isFiltered ? "No matching jobs" : "No jobs recorded"}
          description={
            isFiltered
              ? "Try clearing filters or broadening your seed URL search."
              : "Create a crawl from /crawl. Once workers start crawling and indexing, jobs will appear here."
          }
        />
      ) : null}

      {!loadError && total > 0 ? (
        <>
          <p className="mt-4 font-mono text-xs text-muted">
            Showing {formatJobRange(page, pageSize, total)} of {total.toLocaleString()} job{total === 1 ? "" : "s"}
            {isFiltered ? " (filtered)" : ""}
          </p>
          <section className="mt-3 overflow-hidden rounded border border-rule bg-paper shadow-lift">
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
                        <Link
                          className="text-accent underline decoration-rule underline-offset-4 hover:decoration-accent"
                          href={`/jobs/${job.id}`}
                        >
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

          {totalPages > 1 ? (
            <nav
              className="mt-4 flex flex-col gap-3 border-t border-rule/60 pt-4 sm:flex-row sm:items-center sm:justify-between"
              aria-label="Job list pagination"
            >
              <div className="flex flex-wrap gap-2">
                <PaginationLink
                  disabled={page <= 1}
                  href={`/jobs?${jobsListQueryString({ ...queryBase, page: page - 1 })}`}
                  label="Previous"
                />
                <PaginationLink
                  disabled={page >= totalPages}
                  href={`/jobs?${jobsListQueryString({ ...queryBase, page: page + 1 })}`}
                  label="Next"
                />
              </div>
              <p className="font-mono text-xs text-muted">
                Page {page} of {totalPages}
              </p>
            </nav>
          ) : null}
        </>
      ) : null}
    </article>
  );
}

function formatJobRange(page: number, pageSize: number, total: number): string {
  const start = total === 0 ? 0 : (page - 1) * pageSize + 1;
  const end = Math.min(page * pageSize, total);
  return `${start.toLocaleString()}–${end.toLocaleString()}`;
}

function PaginationLink({ href, label, disabled }: { href: string; label: string; disabled: boolean }) {
  if (disabled) {
    return (
      <span className="rounded border border-rule/50 px-3 py-1.5 text-sm text-muted opacity-50">{label}</span>
    );
  }
  return (
    <Link
      href={href}
      className="rounded border border-rule px-3 py-1.5 text-sm text-ink transition-colors hover:border-accent hover:text-accent"
    >
      {label}
    </Link>
  );
}
