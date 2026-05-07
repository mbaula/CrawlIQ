"use client";

import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";

import { createCrawlJob } from "@/lib/api";

type CrawlFormState = {
  seedUrl: string;
  maxPages: number;
  maxDepth: number;
  sameDomainOnly: boolean;
};

function validateUrl(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) return "Seed URL is required.";
  try {
    const parsed = new URL(trimmed);
    if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
      return "Seed URL must start with http:// or https://.";
    }
    return null;
  } catch {
    return "Seed URL must be a valid URL.";
  }
}

export function CrawlJobForm() {
  const router = useRouter();
  const [form, setForm] = useState<CrawlFormState>({
    seedUrl: "",
    maxPages: 100,
    maxDepth: 2,
    sameDomainOnly: true,
  });
  const [submitting, setSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const seedUrlError = useMemo(() => validateUrl(form.seedUrl), [form.seedUrl]);

  async function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setErrorMessage(null);

    const urlError = validateUrl(form.seedUrl);
    if (urlError) {
      setErrorMessage(urlError);
      return;
    }

    setSubmitting(true);
    try {
      const created = await createCrawlJob({
        seed_url: form.seedUrl.trim(),
        max_pages: form.maxPages,
        max_depth: form.maxDepth,
        same_domain_only: form.sameDomainOnly,
      });
      router.push(`/jobs/${created.id}`);
    } catch (error) {
      setErrorMessage(error instanceof Error ? error.message : "Failed to create crawl job.");
      setSubmitting(false);
    }
  }

  return (
    <form onSubmit={onSubmit} className="mt-8 max-w-measure space-y-6">
      <fieldset disabled={submitting} className="space-y-5">
        <div>
          <label className="block font-mono text-[11px] uppercase tracking-widest text-muted" htmlFor="seed-url">
            Seed URL
          </label>
          <input
            id="seed-url"
            name="seed-url"
            type="url"
            inputMode="url"
            placeholder="https://docs.example.com/"
            className={[
              "mt-2 w-full rounded border bg-paper px-3 py-2 text-sm text-ink shadow-lift outline-none transition-colors",
              seedUrlError ? "border-danger/60 focus:border-danger" : "border-rule focus:border-accent",
            ].join(" ")}
            value={form.seedUrl}
            onChange={(e) => setForm((prev) => ({ ...prev, seedUrl: e.target.value }))}
            required
          />
          {seedUrlError ? (
            <p className="mt-2 text-xs text-danger">{seedUrlError}</p>
          ) : (
            <p className="mt-2 text-xs text-muted">Start URL for the crawl frontier (depth 0).</p>
          )}
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-widest text-muted" htmlFor="max-pages">
              Max pages
            </label>
            <input
              id="max-pages"
              name="max-pages"
              type="number"
              min={1}
              max={10000}
              className="mt-2 w-full rounded border border-rule bg-paper px-3 py-2 text-sm text-ink shadow-lift outline-none transition-colors focus:border-accent"
              value={form.maxPages}
              onChange={(e) => setForm((prev) => ({ ...prev, maxPages: Number(e.target.value) }))}
              required
            />
          </div>
          <div>
            <label className="block font-mono text-[11px] uppercase tracking-widest text-muted" htmlFor="max-depth">
              Max depth
            </label>
            <input
              id="max-depth"
              name="max-depth"
              type="number"
              min={0}
              max={10}
              className="mt-2 w-full rounded border border-rule bg-paper px-3 py-2 text-sm text-ink shadow-lift outline-none transition-colors focus:border-accent"
              value={form.maxDepth}
              onChange={(e) => setForm((prev) => ({ ...prev, maxDepth: Number(e.target.value) }))}
              required
            />
          </div>
        </div>

        <label className="flex items-center gap-3">
          <input
            type="checkbox"
            checked={form.sameDomainOnly}
            onChange={(e) => setForm((prev) => ({ ...prev, sameDomainOnly: e.target.checked }))}
            className="h-4 w-4 rounded border-rule bg-paper text-accent focus:ring-accent"
          />
          <span className="text-sm text-ink">Same-domain only</span>
        </label>
      </fieldset>

      {errorMessage ? (
        <section className="rounded border border-danger/40 bg-danger/10 p-4 text-sm text-ink">
          <p className="font-medium">Couldn’t create crawl job</p>
          <p className="mt-1 text-xs text-muted">{errorMessage}</p>
        </section>
      ) : null}

      <div className="flex items-center gap-3">
        <button
          type="submit"
          disabled={submitting}
          className="rounded bg-accent px-4 py-2 text-sm font-medium text-paper shadow-lift transition-colors hover:bg-accent/90 disabled:cursor-not-allowed disabled:bg-rule"
        >
          {submitting ? "Creating…" : "Create crawl job"}
        </button>
        <p className="text-xs text-muted">
          This will enqueue background work. You’ll be redirected to the job detail page.
        </p>
      </div>
    </form>
  );
}

