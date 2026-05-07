/**
 * Base URL for the CrawlIQ HTTP API (browser + server).
 * Set in `.env` / Docker: `NEXT_PUBLIC_API_URL` (no trailing slash).
 */
export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!raw) return "http://localhost:8000";
  return raw.replace(/\/$/, "");
}

export type CrawlJobCreateRequest = {
  seed_url: string;
  max_pages: number;
  max_depth: number;
  same_domain_only: boolean;
};

export type CrawlJobCreateResponse = {
  id: number;
  seed_url: string;
  status: string;
  max_pages: number;
  max_depth: number;
  same_domain_only: boolean;
  created_at: string;
  enqueued: boolean;
};

export async function createCrawlJob(body: CrawlJobCreateRequest): Promise<CrawlJobCreateResponse> {
  const response = await fetch(`${getApiBaseUrl()}/crawl-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API error (${response.status})`);
  }

  return (await response.json()) as CrawlJobCreateResponse;
}
