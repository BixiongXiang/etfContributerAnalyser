/**
 * Shared TypeScript types — mirrors the FastAPI response shapes.
 * Import from @/lib/types throughout the frontend.
 */

export interface ETFSummary {
  symbol: string;
  name: string;
  last_updated: string | null; // ISO datetime string
  today_return_pct: number | null;
}

export interface ContributorRow {
  symbol: string;
  company_name: string;
  weight: number;       // %, e.g. 8.2
  return_pct: number;   // %, e.g. -3.1
  contribution: number; // percentage points, e.g. -0.254
  sector: string | null;
  pct_of_total_move: number; // %, e.g. 20.5
  price: number | null; // latest close price in USD
}

export interface SectorRow {
  sector: string;
  contribution: number;       // pp
  pct_of_total_move: number;  // %
  num_stocks: number;
}

export interface AttributionResponse {
  etf: string;
  date: string; // YYYY-MM-DD
  etf_return_pct: number;
  data_as_of: string; // ISO datetime
  etf_price: number | null;  // ETF close price for the day
  top_negative: ContributorRow[];
  top_positive: ContributorRow[];
  sector_attribution: SectorRow[];
}

export interface SummaryResponse {
  etf: string;
  date: string;
  summary: string;
}

export interface HealthResponse {
  status: string;
  timestamp: string;
}

/** Response from GET /api/attribution/{symbol}/available-dates */
export interface AvailableDatesResponse {
  etf: string;
  dates: string[];    // YYYY-MM-DD strings
  earliest: string;   // YYYY-MM-DD
  latest: string;     // YYYY-MM-DD
}

/** Response from GET /api/attribution/{symbol}/range */
export interface RangeAttributionResponse {
  etf: string;
  start_date: string;   // YYYY-MM-DD
  end_date: string;     // YYYY-MM-DD
  etf_return_pct: number;
  etf_price_start: number | null;  // ETF close on first trading day in range
  etf_price_end: number | null;    // ETF close on last trading day in range
  top_negative: ContributorRow[];
  top_positive: ContributorRow[];
  sector_attribution: SectorRow[];
}
