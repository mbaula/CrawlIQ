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

export type CrawlJobBulkCreateRequest = {
  seed_urls: string[];
  max_pages: number;
  max_depth: number;
  same_domain_only: boolean;
};

export type CrawlJobBulkCreateItem = {
  seed_url: string;
  ok: boolean;
  job: CrawlJobCreateResponse | null;
  error: string | null;
};

export type CrawlJobBulkCreateResponse = {
  results: CrawlJobBulkCreateItem[];
};

export async function bulkCreateCrawlJobs(body: CrawlJobBulkCreateRequest): Promise<CrawlJobBulkCreateResponse> {
  const response = await fetch(`${getApiBaseUrl()}/crawl-jobs/bulk`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API error (${response.status})`);
  }

  return (await response.json()) as CrawlJobBulkCreateResponse;
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

export type CrawlJobListRead = {
  items: CrawlJobRead[];
  total: number;
  limit: number;
  offset: number;
};

export type ListCrawlJobsParams = {
  limit?: number;
  offset?: number;
  status?: string;
  q?: string;
};

export async function listCrawlJobs(params?: ListCrawlJobsParams): Promise<CrawlJobListRead> {
  const limit = params?.limit ?? 50;
  const offset = params?.offset ?? 0;
  const url = new URL(`${getApiBaseUrl()}/crawl-jobs`);
  url.searchParams.set("limit", String(limit));
  url.searchParams.set("offset", String(offset));
  if (params?.status) {
    url.searchParams.set("status", params.status);
  }
  const q = params?.q?.trim();
  if (q) {
    url.searchParams.set("q", q);
  }
  const response = await fetch(url.toString(), {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    cache: "no-store",
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `API error (${response.status})`);
  }
  return (await response.json()) as CrawlJobListRead;
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

export type CrawlJobRetryResponse = {
  id: number;
  status: string;
  enqueued: boolean;
};

export async function retryCrawlJob(jobId: number): Promise<CrawlJobRetryResponse> {
  return await fetchJsonOrThrow<CrawlJobRetryResponse>(`${getApiBaseUrl()}/crawl-jobs/${jobId}/retry`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
  });
}

export type RelatedPageRead = {
  page_id: number;
  title: string | null;
  url: string;
  edge_type: string;
  strength: number;
  reason: string;
};

export type GraphScoreComponentsRead = {
  bm25_raw: number;
  bm25_norm: number;
  pagerank_norm: number;
  neighbor_boost_raw: number;
  neighbor_boost_norm: number;
  duplicate_penalty_raw: number;
  duplicate_penalty_norm: number;
  final_score: number;
};

export type SearchResultItem = {
  page_id: number;
  title: string | null;
  url: string;
  score: number;
  snippet: string;
  matched_terms: string[];
  related: RelatedPageRead[];
  score_components?: GraphScoreComponentsRead | null;
  score_explanation?: string | null;
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
  include_related?: boolean;
  related_limit?: number;
  graph_enhanced?: boolean;
}): Promise<SearchResponse> {
  const query = params.q.trim();
  const limit = params.limit ?? 20;
  const url = new URL(`${getApiBaseUrl()}/search`);
  url.searchParams.set("q", query);
  url.searchParams.set("limit", String(limit));
  if (typeof params.job_id === "number") {
    url.searchParams.set("job_id", String(params.job_id));
  }
  if (params.include_related) {
    url.searchParams.set("include_related", "true");
    const rl = params.related_limit ?? 3;
    url.searchParams.set("related_limit", String(rl));
  }
  if (params.graph_enhanced) {
    url.searchParams.set("graph_enhanced", "true");
  }
  return await fetchJsonOrThrow<SearchResponse>(url.toString(), {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
}

export type DomainCount = { domain: string; page_count: number };
export type ErrorTypeCount = { error_type: string; count: number };
export type HttpStatusCount = { status_code: number; count: number };
export type QueryCount = { query: string; count: number };
export type FailedUrlRead = {
  url: string;
  error_type: string;
  error_message: string | null;
  created_at: string;
};
export type LargestPageRead = {
  page_id: number;
  url: string;
  title: string | null;
  token_count: number;
};
export type SearchQueryRead = {
  query: string;
  result_count: number;
  latency_ms: number;
  created_at: string;
};
export type HttpStatusClassTotals = {
  status_2xx: number;
  status_3xx: number;
  status_4xx: number;
  status_5xx: number;
};

export type DomainFailureCount = {
  domain: string;
  failure_count: number;
};

export type CrawlStatsRead = {
  total_urls_attempted: number;
  total_pages_crawled: number;
  total_pages_indexed: number;
  pages_pending_indexing: number;
  skipped_urls_count: number;
  policy_rejected_urls_count: number;
  total_skipped_rows: number;
  fetch_failure_row_count: number;
  total_crawl_jobs: number;
  total_failures: number;
  failed_url_count: number;
  crawl_success_rate: number;
  avg_pages_per_job: number;
  avg_crawl_duration_seconds: number | null;
  index_coverage: number;
  unique_terms: number;
  total_postings: number;
  avg_terms_per_page: number;
  median_terms_per_page: number;
  p95_terms_per_page: number;
  largest_page: LargestPageRead | null;
  last_indexed_at: string | null;
  avg_fetch_latency_ms: number | null;
  p95_fetch_latency_ms: number | null;
  total_searches: number;
  zero_result_searches: number;
  zero_result_rate: number;
  avg_results_per_search: number;
  searches_hitting_result_cap: number;
  average_search_latency_ms: number;
  p95_search_latency_ms: number;
  slowest_search_latency_ms: number | null;
  slowest_search_query: string | null;
  recent_searches: SearchQueryRead[];
  recent_zero_result_searches: SearchQueryRead[];
  top_queries: QueryCount[];
  top_crawled_domains: DomainCount[];
  skipped_breakdown: ErrorTypeCount[];
  fetch_failures_breakdown: ErrorTypeCount[];
  failures_by_type: ErrorTypeCount[];
  http_status_distribution: HttpStatusCount[];
  http_status_class_totals: HttpStatusClassTotals;
  recent_failed_urls: FailedUrlRead[];
  rate_limited_url_count: number;
  timeout_fetch_count: number;
  top_failure_domains: DomainFailureCount[];
};

export async function getStats(): Promise<CrawlStatsRead> {
  return await fetchJsonOrThrow<CrawlStatsRead>(`${getApiBaseUrl()}/stats`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
  });
}
