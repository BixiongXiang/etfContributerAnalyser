/**
 * API client — thin wrapper around fetch() for all backend calls.
 * All requests go to /api/* which Next.js proxies to FastAPI.
 */

import type {
  AttributionResponse,
  ETFSummary,
  SummaryResponse,
  HealthResponse,
} from "@/lib/types";

const BASE = "/api";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    next: { revalidate: 60 }, // ISR: cache for 60s
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

/** List all supported ETFs. */
export async function fetchETFs(): Promise<ETFSummary[]> {
  return get<ETFSummary[]>("/etfs");
}

/**
 * Fetch attribution data for an ETF.
 * @param symbol  e.g. "QQQ"
 * @param date    YYYY-MM-DD, or undefined for latest available
 */
export async function fetchAttribution(
  symbol: string,
  date?: string
): Promise<AttributionResponse> {
  const qs = date ? `?date=${date}` : "";
  return get<AttributionResponse>(`/attribution/${symbol}${qs}`);
}

/** Fetch the rule-based text summary for an ETF. */
export async function fetchSummary(
  symbol: string,
  date?: string
): Promise<SummaryResponse> {
  const qs = date ? `?date=${date}` : "";
  return get<SummaryResponse>(`/summary/${symbol}${qs}`);
}

/** Health check. */
export async function fetchHealth(): Promise<HealthResponse> {
  return get<HealthResponse>("/health");
}
