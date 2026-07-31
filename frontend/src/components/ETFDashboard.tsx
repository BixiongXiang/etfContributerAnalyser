"use client";

/**
 * ETFDashboard — main page component.
 *
 * Renders:
 * - ETF selector tabs (QQQ / VOO / SCHD)
 * - Today's return + data freshness indicator
 * - Sector summary
 * - Top Negative / Top Positive contributor tables
 * - Rule-based text summary
 *
 * Attribution data is fetched client-side so the page stays interactive.
 * Server renders the ETF list (from the homepage Server Component).
 */

import { useState, useEffect } from "react";
import type { AttributionResponse, ETFSummary, SummaryResponse } from "@/lib/types";
import { fetchAttribution, fetchSummary } from "@/lib/api";
import ContributorTable from "@/components/ContributorTable";
import SectorSummary from "@/components/SectorSummary";
import DataFreshnessTag from "@/components/DataFreshnessTag";

const SUPPORTED = ["QQQ", "VOO", "SCHD"] as const;

interface Props {
  etfs: ETFSummary[];
}

export default function ETFDashboard({ etfs }: Props) {
  const [selected, setSelected] = useState<string>("QQQ");
  const [attribution, setAttribution] = useState<AttributionResponse | null>(null);
  const [summary, setSummary] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setLoading(true);
    setError(null);
    setAttribution(null);
    setSummary(null);

    Promise.all([
      fetchAttribution(selected),
      fetchSummary(selected),
    ])
      .then(([attr, summ]) => {
        setAttribution(attr);
        setSummary(summ.summary);
      })
      .catch((e) => {
        setError(
          e.message?.includes("501")
            ? "Attribution data not yet available — the backend pipeline is still being built."
            : `Failed to load data: ${e.message}`
        );
      })
      .finally(() => setLoading(false));
  }, [selected]);

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
      <div className="flex items-baseline justify-between">
        <div>
          <h2 className="text-2xl font-bold">{selected}</h2>
          {etfMeta?.today_return_pct !== undefined && etfMeta.today_return_pct !== null ? (
            <p
              className={`text-lg font-semibold ${
                etfMeta.today_return_pct >= 0 ? "text-green-600" : "text-red-600"
              }`}
            >
              {etfMeta.today_return_pct >= 0 ? "+" : ""}
              {etfMeta.today_return_pct.toFixed(2)}% today
            </p>
          ) : null}
        </div>
        {etfMeta?.last_updated && (
          <DataFreshnessTag isoTimestamp={etfMeta.last_updated} />
        )}
      </div>

      {/* Loading / error states */}
      {loading && (
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
