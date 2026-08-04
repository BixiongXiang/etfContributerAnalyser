"use client";

/**
 * DateRangePicker — lets the user select a start and end date.
 *
 * - Available dates are fetched from /api/attribution/{symbol}/available-dates
 * - Dates outside the available set are disabled via min/max attributes
 * - Default: start = end = latest available date  (single-day mode)
 * - When start == end it is effectively a single-day view
 * - Parent is notified via onRangeChange whenever Apply is clicked
 */

import { useState, useEffect } from "react";
import type { AvailableDatesResponse } from "@/lib/types";
import { fetchAvailableDates } from "@/lib/api";

interface DateRange {
  start: string;
  end: string;
}

interface Props {
  symbol: string;
  onRangeChange: (range: DateRange) => void;
  loading?: boolean;
}

export default function DateRangePicker({ symbol, onRangeChange, loading }: Props) {
  const [availableDates, setAvailableDates] = useState<AvailableDatesResponse | null>(null);
  const [datesLoading, setDatesLoading] = useState(true);
  const [datesError, setDatesError] = useState<string | null>(null);
  const [draftStart, setDraftStart] = useState<string>("");
  const [draftEnd, setDraftEnd] = useState<string>("");
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => {
    setDatesLoading(true);
    setDatesError(null);
    fetchAvailableDates(symbol)
      .then((res) => {
        setAvailableDates(res);
        setDraftStart(res.latest);
        setDraftEnd(res.latest);
        setValidationError(null);
      })
      .catch(() => setDatesError("Could not load available dates."))
      .finally(() => setDatesLoading(false));
  }, [symbol]);

  function validate(start: string, end: string): string | null {
    if (!availableDates) return null;
    if (!start || !end) return "Please select both dates.";
    if (start > end) return "Start date must be before or equal to end date.";
    if (start < availableDates.earliest) return `No data before ${availableDates.earliest}.`;
    if (end > availableDates.latest) return `No data after ${availableDates.latest}.`;
    return null;
  }

  function handleStartChange(val: string) {
    setDraftStart(val);
    if (val > draftEnd) setDraftEnd(val);
    setValidationError(null);
  }

  function handleEndChange(val: string) {
    setDraftEnd(val);
    setValidationError(null);
  }

  function handleApply() {
    const err = validate(draftStart, draftEnd);
    if (err) { setValidationError(err); return; }
    onRangeChange({ start: draftStart, end: draftEnd });
  }

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleApply();
  }

  const isSingleDay = draftStart === draftEnd;
  const isDefaultState =
    availableDates !== null &&
    draftStart === availableDates.latest &&
    draftEnd === availableDates.latest;

  if (datesLoading) return <div className="text-xs text-gray-500">Loading dates…</div>;
  if (datesError) return <div className="text-xs text-red-400">{datesError}</div>;
  if (!availableDates) return null;

  const inputClass =
    "rounded-md border border-gray-600 bg-gray-800 px-3 py-1.5 text-sm text-gray-100 " +
    "focus:border-gray-400 focus:outline-none focus:ring-1 focus:ring-gray-500 " +
    "[color-scheme:dark]";

  return (
    <div className="flex flex-wrap items-end gap-3">
      {/* Start date */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-500">From</label>
        <input
          type="date"
          value={draftStart}
          min={availableDates.earliest}
          max={availableDates.latest}
          onChange={(e) => handleStartChange(e.target.value)}
          onKeyDown={handleKeyDown}
          className={inputClass}
        />
      </div>

      {/* End date */}
      <div className="flex flex-col gap-1">
        <label className="text-xs font-medium text-gray-500">To</label>
        <input
          type="date"
          value={draftEnd}
          min={draftStart || availableDates.earliest}
          max={availableDates.latest}
          onChange={(e) => handleEndChange(e.target.value)}
          onKeyDown={handleKeyDown}
          className={inputClass}
        />
      </div>

      {/* Apply button */}
      <button
        onClick={handleApply}
        disabled={loading || isDefaultState}
        className="rounded-md bg-blue-600 px-4 py-1.5 text-sm font-medium text-white
                   hover:bg-blue-500 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? "Loading…" : "Apply"}
      </button>

      {/* Mode indicator */}
      <span className="text-xs text-gray-500 self-center">
        {isSingleDay
          ? "Single day"
          : `Range · ${countTradingDays(availableDates.dates, draftStart, draftEnd)} trading days`}
      </span>

      {validationError && (
        <p className="w-full text-xs text-red-400">{validationError}</p>
      )}
    </div>
  );
}

function countTradingDays(dates: string[], start: string, end: string): number {
  return dates.filter((d) => d >= start && d <= end).length;
}
