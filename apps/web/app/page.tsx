import type { Metadata } from "next";

import { EmptyState } from "@/components/EmptyState";

export const metadata: Metadata = {
  title: "Index",
};

export default function HomePage() {
  return (
    <article>
      <p className="font-mono text-[11px] uppercase tracking-[0.25em] text-muted">Notebook · v0</p>
      <h1 className="mt-3 font-serif text-4xl font-semibold tracking-tight text-ink sm:text-5xl">CrawlIQ</h1>
      <p className="mt-6 max-w-measure text-base leading-relaxed text-muted">
        A precise, bounded crawl through the open web: fetch, extract, index, and search. Documented here.
      </p>
      <div className="mt-10 max-w-measure border-t border-rule pt-6">
        <p className="font-mono text-xs text-muted">Sections</p>
        <ul className="mt-3 space-y-2 font-mono text-sm text-ink">
          <li className="flex gap-3 border-b border-rule/70 pb-2">
            <span className="w-24 shrink-0 text-muted">Crawl</span>
            <span className="text-muted">Seeds, limits, enqueue.</span>
          </li>
          <li className="flex gap-3 border-b border-rule/70 pb-2">
            <span className="w-24 shrink-0 text-muted">Jobs</span>
            <span className="text-muted">Queue state and receipts.</span>
          </li>
          <li className="flex gap-3 border-b border-rule/70 pb-2">
            <span className="w-24 shrink-0 text-muted">Search</span>
            <span className="text-muted">Query against the index.</span>
          </li>
          <li className="flex gap-3 pb-1">
            <span className="w-24 shrink-0 text-muted">Stats</span>
            <span className="text-muted">Counts and health.</span>
          </li>
        </ul>
      </div>
      <EmptyState
        title="Instrument panel not wired"
        description="The shell is in place: navigation, theme, and API configuration. Crawl controls and live data will attach to these routes as the build continues."
      />
    </article>
  );
}
