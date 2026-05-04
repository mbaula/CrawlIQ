import type { Metadata } from "next";
import Link from "next/link";

import { EmptyState } from "@/components/EmptyState";

export const metadata: Metadata = {
  title: "Jobs",
};

export default function JobsPage() {
  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Jobs</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Table of crawl and index jobs: status, timestamps, errors, and links to detail pages.
      </p>
      <p className="mt-4 font-mono text-xs text-muted">
        Sample detail route:{" "}
        <Link className="text-accent underline decoration-rule underline-offset-4 transition-colors hover:decoration-accent" href="/jobs/example">
          /jobs/example
        </Link>
      </p>
      <EmptyState
        title="No jobs recorded"
        description="The queue is quiet. When workers enqueue tasks, rows will appear here with stable IDs for deep links."
      />
    </article>
  );
}
