"use client";

/**
 * ETFDashboard — main page component.
 *
 * Modes:
 *  - Live / latest:  calls /api/attribution/{symbol}/live  (auto-refreshes every 30 min)
 *  - Date range:     calls /api/attribution/{symbol}/range  (no auto-refresh)
 *
 * The DateRangePicker defaults to latest available date (single-day).
 * When the user picks a range and hits Apply, the dashboard switches to range mode.
 * The LIVE / CLOSED badge only shows in live mode.
 */

import { useState, useEffect, useCallback, useRef } from "react";
import type {
  AttributionResponse,
  RangeAttributionResponse,
  ETFSummary,
  SummaryResponse,
} from "@/lib/types";
import { fetchSummary, fetchETFs, fetchRangeAttribution } from "@/lib/api";
import ContributorTable from "@/components/ContributorTable";
import SectorSummary from "@/components/SectorSummary";
import DataFreshnessTag from "@/components/DataFreshnessTag";
import DateRangePicker from "@/components/DateRangePicker";

const SUPPORTED = ["QQQ", "VOO", "SCHD"] as const;
const REFRESH_INTERVAL_MS = 30 * 60 * 1000; // 30 minutes

/** Determine if US markets are likely open based on browser local time converted to ET. */
function isMarketHours(): boolean {
  const now = new Date();
  const etString = now.toLocaleString("en-US", { timeZone: "America/New_York" });
  const et = new Date(etString);
  const day = et.getDay();
  const totalMinutes = et.getHours() * 60 + et.getMinutes();
  return day >= 1 && day <= 5 && totalMinutes >= 9 * 60 + 30 && totalMinutes < 16 * 60;
}

/** Normalise RangeAttributionResponse into the AttributionResponse shape for display. */
function toAttributionResponse(
  r: RangeAttributionResponse
): AttributionResponse {
  return {
    etf: r.etf,
    date: r.start_date === r.end_date ? r.start_date : `${r.start_date} to ${r.end_date}`,
    etf_return_pct: r.etf_return_pct,
    data_as_of: "",
    top_negative: r.top_negative,
    top_positive: r.top_positive,
    sector_attribution: r.sector_attribution,
  };
}

interface DateRange {
  start: string;
  end: string;
}

interface Props {
  etfs: ETFSummary[];
}

export default function ETFDashboard({ etfs: _ }: Props) {
  const [etfs, setEtfs] = useState<ETFSummary[]>([]);
  const [selected, setSelected] = useState<string>("QQQ");
  const [attribution, setAttribution] = useState<AttributionResponse | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastRefreshed, setLastRefreshed] = useState<Date | null>(null);
  const [isLive, setIsLive] = useState(false);

  // Date range state — null means "live / latest" mode
  const [activeRange, setActiveRange] = useState<DateRange | null>(null);
  const isRangeMode = activeRange !== null;

  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch ETF metadata once on mount
  useEffect(() => {
    fetchETFs().then(setEtfs).catch(() => {});
  }, []);

  const loadLiveData = useCallback(async (sym: string) => {
    setLoading(true);
    setError(null);
    const live = isMarketHours();
    setIsLive(live);

    try {
      const [attrRes, summRes] = await Promise.all([
        fetch(`/api/attribution/${sym}/live`).then((r) => {
          if (!r.ok) throw new Error(`${r.status}`);
          return r.json() as Promise<AttributionResponse>;
        }),
        fetchSummary(sym),
      ]);
      setAttribution(attrRes);
      setSummary(summRes.summary);
      setLastRefreshed(new Date());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes("404")
          ? "Attribution data not yet available — run /api/admin/backfill first."
          : `Failed to load data: ${msg}`
      );
    } finally {
      setLoading(false);
    }
  }, []);

  const loadRangeData = useCallback(async (sym: string, range: DateRange) => {
    setLoading(true);
    setError(null);
    setIsLive(false);

    try {
      const rangeRes = await fetchRangeAttribution(sym, range.start, range.end);
      setAttribution(toAttributionResponse(rangeRes));
      setSummary(null); // text summary not available for ranges
      setLastRefreshed(new Date());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes("404")
          ? `No data found for ${sym} in the selected range.`
          : `Failed to load data: ${msg}`
      );
    } finally {
      setLoading(false);
    }
  }, []);

  // Load data when selected ETF changes or range changes
  useEffect(() => {
    if (isRangeMode && activeRange) {
      loadRangeData(selected, activeRange);
    } else {
      loadLiveData(selected);
    }
  }, [selected, activeRange, isRangeMode, loadLiveData, loadRangeData]);

  // Auto-refresh every 30 min — only in live mode
  useEffect(() => {
    if (isRangeMode) return; // no auto-refresh in range mode

    const scheduleNext = () => {
      timerRef.current = setTimeout(() => {
        if (!document.hidden) loadLiveData(selected);
        scheduleNext();
      }, REFRESH_INTERVAL_MS);
    };

    const handleVisibility = () => {
      if (!document.hidden) loadLiveData(selected);
    };

    document.addEventListener("visibilitychange", handleVisibility);
    scheduleNext();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [selected, isRangeMode, loadLiveData]);

  function handleRangeChange(range: DateRange) {
    setActiveRange(range);
  }

  function handleBackToLive() {
    setActiveRange(null);
  }

  // Label for the return figure
  function returnLabel(): string {
    if (isRangeMode && activeRange) {
      if (activeRange.start === activeRange.end) return `(${activeRange.start})`;
      return `(${activeRange.start} – ${activeRange.end})`;
    }
    return isLive ? "(intraday)" : "(close)";
  }

  return (
    <div className="space-y-6">
      {/* ETF selector */}
      <div className="flex items-center gap-2">
        {SUPPORTED.map((sym) => (
          <button
            key={sym}
            onClick={() => setSelected(sym)}
            className={`rounded-md px-4 py-2 text-sm font-medium transition-colors ${
              selected === sym
                ? "bg-gray-900 text-white"
                : "bg-white text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50"
            }`}
          >
            {sym}
          </button>
        ))}
      </div>

      {/* Date range picker */}
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <DateRangePicker
          symbol={selected}
          onRangeChange={handleRangeChange}
          loading={loading}
        />
        {isRangeMode && (
          <button
            onClick={handleBackToLive}
            className="mt-3 text-xs text-blue-600 hover:underline"
          >
            ← Back to live / latest
          </button>
        )}
      </div>

      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold">{selected}</h2>

            {/* LIVE / CLOSED badge — only in live mode */}
            {!isRangeMode && (
              <span
                className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold ${
                  isLive
                    ? "bg-green-100 text-green-700"
                    : "bg-gray-100 text-gray-500"
                }`}
              >
                {isLive && (
                  <span className="h-1.5 w-1.5 rounded-full bg-green-500 animate-pulse" />
                )}
                {isLive ? "LIVE" : "CLOSED"}
              </span>
            )}

            {/* Range badge */}
            {isRangeMode && (
              <span className="inline-flex items-center rounded-full bg-blue-100 px-2.5 py-0.5 text-xs font-semibold text-blue-700">
                RANGE
              </span>
            )}
          </div>

          {attribution && (
            <p
              className={`text-lg font-semibold ${
                attribution.etf_return_pct >= 0 ? "text-green-600" : "text-red-600"
              }`}
            >
              {attribution.etf_return_pct >= 0 ? "+" : ""}
              {attribution.etf_return_pct.toFixed(2)}%{" "}
              <span className="text-sm font-normal text-gray-500">{returnLabel()}</span>
            </p>
          )}
        </div>

        <div className="flex flex-col items-end gap-1">
          {lastRefreshed && (
            <span className="text-xs text-gray-400">
              Refreshed{" "}
              {lastRefreshed.toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })}
            </span>
          )}
          {!isRangeMode && isLive && (
            <span className="text-xs text-gray-400">Auto-refreshes every 30 min</span>
          )}
          {!isRangeMode && attribution?.data_as_of && (
            <DataFreshnessTag isoTimestamp={attribution.data_as_of} />
          )}
          {/* Manual refresh — live mode only */}
          {!isRangeMode && (
            <button
              onClick={() => loadLiveData(selected)}
              disabled={loading}
              className="mt-1 rounded px-2 py-1 text-xs text-gray-500 ring-1 ring-gray-200 hover:bg-gray-50 disabled:opacity-40"
            >
              {loading ? "Refreshing…" : "↻ Refresh now"}
            </button>
          )}
        </div>
      </div>

      {/* Loading / error states */}
      {loading && !attribution && (
        <p className="text-sm text-gray-500">Loading attribution data…</p>
      )}
      {error && (
        <div className="rounded-lg border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
          {error}
        </div>
      )}

      {attribution && (
        <>
          {/* Sector summary */}
          <SectorSummary sectors={attribution.sector_attribution} />

          {/* Contributor tables */}
          <div className="grid gap-6 lg:grid-cols-2">
            <ContributorTable
              title="Top Negative Contributors"
              rows={attribution.top_negative}
              variant="negative"
            />
            <ContributorTable
              title="Top Positive Contributors"
              rows={attribution.top_positive}
              variant="positive"
            />
          </div>

          {/* Text summary — only available in live mode */}
          {summary && (
            <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700">
              <p className="mb-1 font-medium text-gray-900">Summary</p>
              <p>{summary}</p>
            </div>
          )}

          {/* Range note */}
          {isRangeMode && (
            <p className="text-xs text-gray-400">
              Cumulative return and contribution are summed across all trading days in the selected range.
              Return % per stock is calculated from actual price change (first → last close in range).
            </p>
          )}
        </>
      )}
    </div>
  );
}
