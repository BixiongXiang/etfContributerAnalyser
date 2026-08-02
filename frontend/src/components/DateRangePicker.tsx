"use client";

/**
 * DateRangePicker — lets the user select a start and end date.
 *
 * - Available dates are fetched from /api/attribution/{symbol}/available-dates
 * - Dates outside the available set are disabled (grayed out via min/max + validation)
 * - Default: start = end = latest available date  (single-day mode)
 * - When start == end it is effectively a single-day view
 * - Parent is notified via onRangeChange whenever a valid range is committed
 */

import { useState, useEffect } from "react";
import type { AvailableDatesResponse } from "@/lib/types";
import { fetchAvailableDates } from "@/lib/api";

interface DateRange {
  start: string; // YYYY-MM-DD
  end: string;   // YYYY-MM-DD
}

interface Props {
  symbol: string;
  /** Called when the user confirms a valid range. */
  onRangeChange: (range: DateRange) => void;
  /** Whether a data fetch is in progress (disables Apply button). */
  loading?: boolean;
}

export default function DateRangePicker({ symbol, onRangeChange, loading }: Props) {
  const [availableDates, setAvailableDates] = useState<AvailableDatesResponse | null>(null);
  const [datesLoading, setDatesLoading] = useState(true);
  const [datesError, setDatesError] = useState<string | null>(null);

  // Draft values — not committed until Apply is clicked
  const [draftStart, setDraftStart] = useState<string>("");
  const [draftEnd, setDraftEnd] = useState<string>("");

  const [validationError, setValidationError] = useState<string | null>(null);

  // Fetch available dates whenever the symbol changes
  useEffect(() => {
    setDatesLoading(true);
    setDatesError(null);
    fetchAvailableDates(symbol)
      .then((res) => {
        setAvailableDates(res);
        // Default to latest available date for both start and end
        setDraftStart(res.latest);
        setDraftEnd(res.latest);
        setValidationError(null);
      })
      .catch(() => {
        setDatesError("Could not load available dates.");
      })
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
    // If new start is after current end, snap end to start
    if (val > draftEnd) setDraftEnd(val);
    setValidationError(null);
  }

  function handleEndChange(val: string) {
    setDraftEnd(val);
    setValidationError(null);
  }

  function handleApply() {
    const err = validate(draftStart, draftEnd);
    if (err) {
      setValidationError(err);
      return;
    }
    onRangeChange({ start: draftStart, end: draftEnd });
  }

  // Allow pressing Enter on either input to apply
  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Enter") handleApply();
  }

  const isSingleDay = draftStart === draftEnd;
  const isDefaultState =
    availableDates !== null &&
    draftStart === availableDates.latest &&
    draftEnd === availableDates.latest;

  if (datesLoading) {
    return <div className="text-xs text-gray-400">Loading dates…</div>;
  }

  if (datesError) {
    return <div className="text-xs text-red-500">{datesError}</div>;
  }

  if (!availableDates) return null;

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
          className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-900
                     focus:border-gray-400 focus:outline-none focus:ring-1 focus:ring-gray-300"
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
          className="rounded-md border border-gray-200 bg-white px-3 py-1.5 text-sm text-gray-900
                     focus:border-gray-400 focus:outline-none focus:ring-1 focus:ring-gray-300"
        />
      </div>

      {/* Apply button */}
      <button
        onClick={handleApply}
        disabled={loading || isDefaultState}
        className="rounded-md bg-gray-900 px-4 py-1.5 text-sm font-medium text-white
                   hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
      >
        {loading ? "Loading…" : "Apply"}
      </button>

      {/* Mode indicator */}
      <span className="text-xs text-gray-400 self-center">
        {isSingleDay ? "Single day" : `Range · ${countTradingDays(availableDates.dates, draftStart, draftEnd)} trading days`}
      </span>

      {/* Validation error */}
      {validationError && (
        <p className="w-full text-xs text-red-500">{validationError}</p>
      )}
    </div>
  );
}

/** Count how many available dates fall within [start, end]. */
function countTradingDays(dates: string[], start: string, end: string): number {
  return dates.filter((d) => d >= start && d <= end).length;
}
