import type { Metadata } from "next";

import { SearchClient } from "@/components/SearchClient";

export const metadata: Metadata = {
  title: "Search",
};

type Props = {
  searchParams?: Record<string, string | string[] | undefined>;
};

function firstParam(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) return value[0];
  return value;
}

export default function SearchPage({ searchParams }: Props) {
  const initialQuery = (firstParam(searchParams?.q) ?? "").toString();
  const rawJobId = firstParam(searchParams?.job_id);
  const parsedJobId = rawJobId ? Number(rawJobId) : NaN;
  const initialJobId = Number.isFinite(parsedJobId) && parsedJobId > 0 ? Math.floor(parsedJobId) : null;

  return (
    <article>
      <h1 className="font-serif text-3xl font-semibold tracking-tight text-ink sm:text-4xl">Search</h1>
      <p className="mt-3 max-w-measure text-sm leading-relaxed text-muted">
        Keyword query against the local index, ranked with BM25 and returned with snippets and matched terms.
      </p>
      <SearchClient initialQuery={initialQuery} initialJobId={initialJobId} />
    </article>
  );
}
