/**
 * Base URL for the CrawlIQ HTTP API (browser + server).
 * Set in `.env` / Docker: `NEXT_PUBLIC_API_URL` (no trailing slash).
 */
export function getApiBaseUrl(): string {
  const raw = process.env.NEXT_PUBLIC_API_URL?.trim();
  if (!raw) return "http://localhost:8000";
  return raw.replace(/\/$/, "");
}
