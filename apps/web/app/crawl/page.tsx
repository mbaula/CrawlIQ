import type { Metadata } from "next";

import { EmptyState } from "@/components/EmptyState";

export const metadata: Metadata = {
  title: "Crawl",
};

export default function CrawlPage() {
  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Crawl</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Configure seed URLs, depth and page caps, politeness delays, and start a bounded crawl.
      </p>
      <EmptyState
        title="No crawl controls yet"
        description="Forms and validation will live here. Until then, this page is a labeled blank in the notebook."
      />
    </article>
  );
}
