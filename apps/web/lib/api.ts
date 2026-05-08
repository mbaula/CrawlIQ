/**
 * Base URL for the CrawlIQ HTTP API.
 *
 * Server-side (SSR): Uses `API_URL` for Docker-internal networking (e.g., http://api:8000).
 * Client-side: Uses `NEXT_PUBLIC_API_URL` for browser access (e.g., http://localhost:8000).
 */
export function getApiBaseUrl(): string {
  const isServer = typeof window === "undefined";
  const serverUrl = isServer ? process.env.API_URL?.trim() : undefined;
  const publicUrl = process.env.NEXT_PUBLIC_API_URL?.trim();
  const raw = serverUrl || publicUrl;
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

export type CrawlJobRead = {
  id: number;
  seed_url: string;
  normalized_seed_url: string;
  status: string;
  max_pages: number;
  max_depth: number;
  same_domain_only: boolean;
  pages_crawled: number;
  pages_indexed: number;
  pages_failed: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
};

export async function listCrawlJobs(params?: { limit?: number; offset?: number }): Promise<CrawlJobRead[]> {
  const limit = params?.limit ?? 50;
  const offset = params?.offset ?? 0;
  const response = await fetch(`${getApiBaseUrl()}/crawl-jobs?limit=${limit}&offset=${offset}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API error (${response.status})`);
  }
  return (await response.json()) as CrawlJobRead[];
}

export type CrawlJobDetailRead = CrawlJobRead & {
  pages_discovered: number;
  crawl_progress: number;
};

export type PageRead = {
  id: number;
  crawl_job_id: number;
  url: string;
  normalized_url: string;
  domain: string;
  title: string | null;
  raw_html_hash: string | null;
  content_hash: string | null;
  status_code: number | null;
  depth: number;
  fetched_at: string | null;
  indexed_at: string | null;
  created_at: string;
};

export type CrawlErrorRead = {
  id: number;
  crawl_job_id: number;
  url: string;
  normalized_url: string;
  error_type: string;
  error_message: string | null;
  retry_count: number;
  created_at: string;
  updated_at: string;
};

async function fetchJsonOrThrow<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, { cache: "no-store", ...init });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API error (${response.status})`);
  }
  return (await response.json()) as T;
}

export async function getCrawlJob(jobId: number): Promise<CrawlJobDetailRead> {
  return await fetchJsonOrThrow<CrawlJobDetailRead>(`${getApiBaseUrl()}/crawl-jobs/${jobId}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
}

export async function listCrawlJobPages(jobId: number): Promise<PageRead[]> {
  return await fetchJsonOrThrow<PageRead[]>(`${getApiBaseUrl()}/crawl-jobs/${jobId}/pages?limit=500`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
}

export async function listCrawlJobErrors(jobId: number): Promise<CrawlErrorRead[]> {
  return await fetchJsonOrThrow<CrawlErrorRead[]>(`${getApiBaseUrl()}/crawl-jobs/${jobId}/errors?limit=500`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
}

export async function cancelCrawlJob(jobId: number): Promise<CrawlJobDetailRead> {
  return await fetchJsonOrThrow<CrawlJobDetailRead>(`${getApiBaseUrl()}/crawl-jobs/${jobId}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
}

export type SearchResultItem = {
  page_id: number;
  title: string | null;
  url: string;
  score: number;
  snippet: string;
  matched_terms: string[];
};

export type SearchResponse = {
  query: string;
  result_count: number;
  latency_ms: number;
  results: SearchResultItem[];
};

export async function searchPages(params: {
  q: string;
  job_id?: number;
  limit?: number;
}): Promise<SearchResponse> {
  const query = params.q.trim();
  const limit = params.limit ?? 20;
  const url = new URL(`${getApiBaseUrl()}/search`);
  url.searchParams.set("q", query);
  url.searchParams.set("limit", String(limit));
  if (typeof params.job_id === "number") {
    url.searchParams.set("job_id", String(params.job_id));
  }
  return await fetchJsonOrThrow<SearchResponse>(url.toString(), {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
}

export type DomainCount = { domain: string; page_count: number };
export type SearchQueryRead = {
  query: string;
  result_count: number;
  latency_ms: number;
  created_at: string;
};
export type CrawlStatsRead = {
  total_crawl_jobs: number;
  total_pages_crawled: number;
  total_pages_indexed: number;
  total_failures: number;
  failed_url_count: number;
  average_search_latency_ms: number;
  recent_searches: SearchQueryRead[];
  top_crawled_domains: DomainCount[];
};

export async function getStats(): Promise<CrawlStatsRead> {
  return await fetchJsonOrThrow<CrawlStatsRead>(`${getApiBaseUrl()}/stats`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
}
