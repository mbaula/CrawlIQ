import type { Metadata } from "next";

import { CrawlJobForm } from "@/components/CrawlJobForm";

export const metadata: Metadata = {
  title: "Crawl",
};

export default function CrawlPage() {
  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Crawl</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Start a bounded crawl by providing a seed URL and limits. Pages will be persisted, indexed, and immediately
        searchable.
      </p>
      <CrawlJobForm />
    </article>
  );
}
