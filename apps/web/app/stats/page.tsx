import type { Metadata } from "next";

import { EmptyState } from "@/components/EmptyState";

export const metadata: Metadata = {
  title: "Stats",
};

export default function StatsPage() {
  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Stats</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Aggregates: pages fetched, failures, queue depth, index size, and latency sketches.
      </p>
      <EmptyState
        title="No telemetry rendered"
        description="Counters and charts will subscribe to the API when metrics endpoints exist. The page is reserved so navigation stays stable."
      />
    </article>
  );
}
