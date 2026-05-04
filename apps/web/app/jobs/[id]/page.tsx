import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";

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

  return (
    <article>
      <p className="font-mono text-[11px] uppercase tracking-[0.2em] text-muted">
        <Link href="/jobs" className="transition-colors hover:text-accent">
          Jobs
        </Link>
        <span className="text-rule"> / </span>
        <span className="text-ink">{id}</span>
      </p>
      <h1 className="mt-3 font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Job receipt</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Identifier <span className="font-mono text-ink">{id}</span>. This page will show logs, graph edges, and
        retry controls for a single job.
      </p>
      <EmptyState
        title="Receipt not generated"
        description="Job payloads and worker traces are not persisted in the UI yet. This route exists so navigation and URLs stay honest while the backend catches up."
      />
    </article>
  );
}
