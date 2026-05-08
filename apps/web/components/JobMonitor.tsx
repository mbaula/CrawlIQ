"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import { EmptyState } from "@/components/EmptyState";
import { cancelCrawlJob, getCrawlJob, listCrawlJobErrors, listCrawlJobPages, retryCrawlJob, type CrawlJobDetailRead, type CrawlErrorRead, type PageRead } from "@/lib/api";

type Props = {
  jobId: number;
};

function formatTime(iso: string | null) {
  if (!iso) return "—";
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

function StatusBadge({ status }: { status: string }) {
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

function isRunningStatus(status: string) {
  return status === "queued" || status === "pending" || status === "running";
}

export function JobMonitor({ jobId }: Props) {
  const [job, setJob] = useState<CrawlJobDetailRead | null>(null);
  const [pages, setPages] = useState<PageRead[]>([]);
  const [errors, setErrors] = useState<CrawlErrorRead[]>([]);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [cancelling, setCancelling] = useState(false);
  const [retrying, setRetrying] = useState(false);

  const shouldPoll = useMemo(() => (job ? isRunningStatus(job.status) : true), [job]);

  async function loadAll() {
    const [j, p, e] = await Promise.all([getCrawlJob(jobId), listCrawlJobPages(jobId), listCrawlJobErrors(jobId)]);
    setJob(j);
    setPages(p);
    setErrors(e);
  }

  async function onCancel() {
    if (!job || !isRunningStatus(job.status)) return;
    setCancelling(true);
    try {
      await cancelCrawlJob(jobId);
      await loadAll();
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to cancel job.");
    } finally {
      setCancelling(false);
    }
  }

  async function onRetry() {
    if (!job || job.status !== "failed") return;
    setRetrying(true);
    setLoadError(null);
    try {
      await retryCrawlJob(jobId);
      await loadAll();
    } catch (err) {
      setLoadError(err instanceof Error ? err.message : "Failed to retry job.");
    } finally {
      setRetrying(false);
    }
  }

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setLoadError(null);

    loadAll()
      .catch((err) => {
        if (cancelled) return;
        setLoadError(err instanceof Error ? err.message : "Failed to load job.");
      })
      .finally(() => {
        if (cancelled) return;
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  useEffect(() => {
    if (!shouldPoll) return;
    const handle = window.setInterval(() => {
      loadAll().catch(() => {
        // keep previous data; transient errors can happen while worker is busy
      });
    }, 3500);
    return () => window.clearInterval(handle);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId, shouldPoll]);

  if (loading && !job) {
    return (
      <section className="mt-10 border border-dashed border-rule bg-paper p-8 shadow-lift">
        <p className="font-mono text-xs text-muted">Loading job…</p>
      </section>
    );
  }

  if (loadError && !job) {
    return (
      <section className="mt-8 rounded border border-danger/40 bg-danger/10 p-4 text-sm text-ink">
        <p className="font-medium">Couldn’t load job</p>
        <p className="mt-1 text-xs text-muted">{loadError}</p>
      </section>
    );
  }

  if (!job) {
    return (
      <EmptyState
        title="Job not available"
        description="This job could not be loaded. Check the job id and API connectivity."
      />
    );
  }

  return (
    <section className="mt-8 space-y-8">
      <section className="rounded border border-rule bg-paper p-5 shadow-lift">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div className="min-w-0">
            <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Seed URL</p>
            <p className="mt-1 break-words text-sm text-ink">{job.seed_url}</p>
            <p className="mt-2 font-mono text-[11px] uppercase tracking-[0.2em] text-muted">Status</p>
            <div className="mt-2 flex items-center gap-3">
              <StatusBadge status={job.status} />
              {shouldPoll ? <span className="font-mono text-[10px] uppercase tracking-widest text-muted">live</span> : null}
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-3">
              {isRunningStatus(job.status) ? (
                <>
                  <button
                    type="button"
                    onClick={onCancel}
                    disabled={cancelling}
                    className="rounded border border-danger/40 bg-danger/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-danger transition-colors hover:border-danger disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {cancelling ? "Cancelling…" : "Cancel job"}
                  </button>
                  <span className="text-xs text-muted">Stops crawling between pages.</span>
                </>
              ) : job.status === "failed" ? (
                <>
                  <button
                    type="button"
                    onClick={onRetry}
                    disabled={retrying}
                    className="rounded border border-amber-500/30 bg-amber-500/10 px-3 py-1.5 font-mono text-[11px] uppercase tracking-widest text-amber-700 transition-colors hover:border-amber-500 dark:text-amber-300 disabled:cursor-not-allowed disabled:opacity-70"
                  >
                    {retrying ? "Retrying…" : "Retry job"}
                  </button>
                  <span className="text-xs text-muted">Re-queues and restarts this crawl from scratch.</span>
                </>
              ) : null}
            </div>
          </div>
          <dl className="grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-3">
            <div>
              <dt className="font-mono text-[11px] uppercase tracking-widest text-muted">Max pages</dt>
              <dd className="mt-1 font-mono text-xs text-ink">{job.max_pages}</dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] uppercase tracking-widest text-muted">Max depth</dt>
              <dd className="mt-1 font-mono text-xs text-ink">{job.max_depth}</dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] uppercase tracking-widest text-muted">Same domain</dt>
              <dd className="mt-1 font-mono text-xs text-ink">{job.same_domain_only ? "yes" : "no"}</dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] uppercase tracking-widest text-muted">Crawled</dt>
              <dd className="mt-1 font-mono text-xs text-ink">{job.pages_crawled}</dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] uppercase tracking-widest text-muted">Indexed</dt>
              <dd className="mt-1 font-mono text-xs text-ink">{job.pages_indexed}</dd>
            </div>
            <div>
              <dt className="font-mono text-[11px] uppercase tracking-widest text-muted">Failed</dt>
              <dd className="mt-1 font-mono text-xs text-ink">{job.pages_failed}</dd>
            </div>
            <div className="col-span-2 sm:col-span-3">
              <dt className="font-mono text-[11px] uppercase tracking-widest text-muted">Started / finished</dt>
              <dd className="mt-1 text-xs text-muted">
                <span className="font-mono text-ink">{formatTime(job.started_at)}</span>
                <span className="px-2 text-rule">→</span>
                <span className="font-mono text-ink">{formatTime(job.finished_at)}</span>
              </dd>
            </div>
          </dl>
        </div>
        {job.error_message ? (
          <div className="mt-5 rounded border border-danger/40 bg-danger/10 p-4">
            <p className="font-mono text-[11px] uppercase tracking-widest text-danger">Job error</p>
            <p className="mt-2 text-sm text-ink">{job.error_message}</p>
          </div>
        ) : null}
      </section>

      <section className="space-y-3">
        <div className="flex items-end justify-between gap-4">
          <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Crawled pages</h2>
          <p className="font-mono text-[11px] uppercase tracking-widest text-muted">{pages.length} rows</p>
        </div>
        {pages.length === 0 ? (
          <EmptyState title="No pages yet" description="Pages will appear here as the crawl progresses." />
        ) : (
          <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-left text-sm">
                <thead className="bg-rule/20">
                  <tr className="text-muted">
                    <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Depth</th>
                    <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Title</th>
                    <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">URL</th>
                    <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Indexed</th>
                  </tr>
                </thead>
                <tbody>
                  {pages.map((p) => (
                    <tr key={p.id} className="border-t border-rule/60">
                      <td className="px-4 py-3 font-mono text-xs text-ink">{p.depth}</td>
                      <td className="px-4 py-3 text-ink">
                        <span className="block max-w-[34ch] truncate" title={p.title ?? ""}>
                          {p.title ?? "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-ink">
                        <a
                          className="block max-w-[46ch] truncate text-accent underline decoration-rule underline-offset-4 hover:decoration-accent"
                          href={p.url}
                          target="_blank"
                          rel="noreferrer"
                          title={p.url}
                        >
                          {p.url}
                        </a>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted">{p.indexed_at ? "yes" : "no"}</td>
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
          <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Errors</h2>
          <p className="font-mono text-[11px] uppercase tracking-widest text-muted">{errors.length} rows</p>
        </div>
        {errors.length === 0 ? (
          <EmptyState title="No errors recorded" description="If fetch/parse errors occur, they’ll appear here." />
        ) : (
          <section className="overflow-hidden rounded border border-rule bg-paper shadow-lift">
            <div className="overflow-x-auto">
              <table className="min-w-full border-collapse text-left text-sm">
                <thead className="bg-rule/20">
                  <tr className="text-muted">
                    <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Type</th>
                    <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Message</th>
                    <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">URL</th>
                    <th className="px-4 py-3 font-mono text-[11px] uppercase tracking-widest">Retries</th>
                  </tr>
                </thead>
                <tbody>
                  {errors.map((e) => (
                    <tr key={e.id} className="border-t border-rule/60">
                      <td className="px-4 py-3 font-mono text-xs text-ink">{e.error_type}</td>
                      <td className="px-4 py-3 text-ink">
                        <span className="block max-w-[48ch] truncate" title={e.error_message ?? ""}>
                          {e.error_message ?? "—"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-ink">
                        <a
                          className="block max-w-[46ch] truncate text-accent underline decoration-rule underline-offset-4 hover:decoration-accent"
                          href={e.url}
                          target="_blank"
                          rel="noreferrer"
                          title={e.url}
                        >
                          {e.url}
                        </a>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs text-muted">{e.retry_count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}
      </section>

      <div className="flex flex-wrap items-center gap-4 text-xs text-muted">
        <span>
          Tip: search this crawl with{" "}
          <Link
            className="text-accent underline decoration-rule underline-offset-4 hover:decoration-accent"
            href={`/search?job_id=${jobId}`}
          >
            /search
          </Link>
        </span>
        <span className="text-rule">|</span>
      </div>
    </section>
  );
}

