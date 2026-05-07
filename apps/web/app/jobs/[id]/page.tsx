import type { Metadata } from "next";
import Link from "next/link";

import { JobMonitor } from "@/components/JobMonitor";

type Props = {
  params: { id: string };
};

export function generateMetadata({ params }: Props): Metadata {
  return {
    title: `Job ${params.id}`,
  };
}

export default function JobDetailPage({ params }: Props) {
  const { id } = params;
  const jobId = Number(id);

  return (
    <article>
      <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">
        <Link href="/jobs" className="transition-colors hover:text-accent">
          Jobs
        </Link>
        <span className="text-rule"> / </span>
        <span className="text-ink">{id}</span>
      </p>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Crawl job</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Identifier <span className="font-mono text-ink">{id}</span>. Monitor crawl progress, pages, and errors.
      </p>
      {Number.isFinite(jobId) && jobId > 0 ? (
        <JobMonitor jobId={jobId} />
      ) : (
        <section className="mt-10 border border-dashed border-rule bg-paper p-8 shadow-lift transition-colors duration-200">
          <div className="max-w-measure border-l-2 border-accent pl-5">
            <h2 className="font-serif text-xl font-medium tracking-tight text-ink">Invalid job id</h2>
            <p className="mt-3 text-sm leading-relaxed text-muted">
              Expected a numeric id in the URL (for example <span className="font-mono text-ink">/jobs/1</span>).
            </p>
          </div>
        </section>
      )}
    </article>
  );
}
