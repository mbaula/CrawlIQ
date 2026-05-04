import type { Metadata } from "next";

import { EmptyState } from "@/components/EmptyState";

export const metadata: Metadata = {
  title: "Search",
};

export default function SearchPage() {
  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Search</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Plain-language or keyword query against the local index; ranked results with snippets and URLs.
      </p>
      <EmptyState
        title="Index not queryable here yet"
        description="The search box and result list will bind to the API once indexing exists. For now, this page holds the layout and copy only."
      />
    </article>
  );
}
