"use client";

/**
 * ETFDashboard — main page component.
 *
 * - Fetches live attribution from /api/attribution/{symbol}/live
 * - Auto-refreshes every 30 minutes
 * - Pauses refresh when the browser tab is hidden
 * - Shows LIVE badge during market hours, CLOSED outside
 */

import { useState, useEffect, useCallback, useRef } from "react";
import type { AttributionResponse, ETFSummary, SummaryResponse } from "@/lib/types";
import { fetchAttribution, fetchSummary, fetchETFs } from "@/lib/api";
import ContributorTable from "@/components/ContributorTable";
import SectorSummary from "@/components/SectorSummary";
import DataFreshnessTag from "@/components/DataFreshnessTag";

const SUPPORTED = ["QQQ", "VOO", "SCHD"] as const;
const REFRESH_INTERVAL_MS = 30 * 60 * 1000; // 30 minutes

/** Determine if US markets are likely open based on browser local time converted to ET. */
function isMarketHours(): boolean {
  const now = new Date();
  // Convert to ET
  const etString = now.toLocaleString("en-US", { timeZone: "America/New_York" });
  const et = new Date(etString);
  const day = et.getDay(); // 0=Sun, 6=Sat
  const hours = et.getHours();
  const minutes = et.getMinutes();
  const totalMinutes = hours * 60 + minutes;
  const openMinutes = 9 * 60 + 30;  // 9:30 AM
  const closeMinutes = 16 * 60;      // 4:00 PM
  return day >= 1 && day <= 5 && totalMinutes >= openMinutes && totalMinutes < closeMinutes;
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
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Fetch ETF metadata once on mount
  useEffect(() => {
    fetchETFs().then(setEtfs).catch(() => {});
  }, []);

  const loadData = useCallback(async (sym: string) => {
    setLoading(true);
    setError(null);

    const live = isMarketHours();
    setIsLive(live);

    try {
      // Use /live endpoint always — it auto-falls-back outside market hours
      const [attr, summ] = await Promise.all([
        fetch(`/api/attribution/${sym}/live`).then(r => {
          if (!r.ok) throw new Error(`${r.status}`);
          return r.json() as Promise<AttributionResponse>;
        }),
        fetchSummary(sym),
      ]);
      setAttribution(attr);
      setSummary(summ.summary);
      setLastRefreshed(new Date());
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      setError(
        msg.includes("501") || msg.includes("404")
          ? "Attribution data not yet available — run /api/admin/backfill first."
          : `Failed to load data: ${msg}`
      );
    } finally {
      setLoading(false);
    }
  }, []);

  // Load data on mount and when selected ETF changes
  useEffect(() => {
    loadData(selected);
  }, [selected, loadData]);

  // Auto-refresh every 30 minutes, paused when tab is hidden
  useEffect(() => {
    const scheduleNext = () => {
      timerRef.current = setTimeout(() => {
        if (!document.hidden) {
          loadData(selected);
        }
        scheduleNext();
      }, REFRESH_INTERVAL_MS);
    };

    const handleVisibility = () => {
      if (!document.hidden) {
        // Tab became visible — refresh immediately if overdue
        loadData(selected);
      }
    };

    document.addEventListener("visibilitychange", handleVisibility);
    scheduleNext();

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
      document.removeEventListener("visibilitychange", handleVisibility);
    };
  }, [selected, loadData]);

  const etfMeta = etfs.find((e) => e.symbol === selected);

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

      {/* Header row */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-3">
            <h2 className="text-2xl font-bold">{selected}</h2>
            {/* LIVE / CLOSED badge */}
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
          </div>

          {attribution && (
            <p
              className={`text-lg font-semibold ${
                attribution.etf_return_pct >= 0 ? "text-green-600" : "text-red-600"
              }`}
            >
              {attribution.etf_return_pct >= 0 ? "+" : ""}
              {attribution.etf_return_pct.toFixed(2)}%
              {isLive ? " (intraday)" : " (close)"}
            </p>
          )}
        </div>

        <div className="flex flex-col items-end gap-1">
          {lastRefreshed && (
            <span className="text-xs text-gray-400">
              Refreshed {lastRefreshed.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
            </span>
          )}
          {isLive && (
            <span className="text-xs text-gray-400">
              Auto-refreshes every 30 min
            </span>
          )}
          {attribution?.data_as_of && (
            <DataFreshnessTag isoTimestamp={attribution.data_as_of} />
          )}
          {/* Manual refresh button */}
          <button
            onClick={() => loadData(selected)}
            disabled={loading}
            className="mt-1 rounded px-2 py-1 text-xs text-gray-500 ring-1 ring-gray-200 hover:bg-gray-50 disabled:opacity-40"
          >
            {loading ? "Refreshing…" : "↻ Refresh now"}
          </button>
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

          {/* Text summary */}
          {summary && (
            <div className="rounded-lg border border-gray-200 bg-white p-4 text-sm text-gray-700">
              <p className="mb-1 font-medium text-gray-900">Summary</p>
              <p>{summary}</p>
            </div>
          )}
        </>
      )}
    </div>
  );
}
