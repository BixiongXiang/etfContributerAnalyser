/**
 * SectorSummary — horizontal bar chart of sector contributions.
 *
 * Each sector gets a colored bar proportional to its |contribution|.
 * Positive sectors are green, negative sectors are red.
 */

import type { SectorRow } from "@/lib/types";

interface Props {
  sectors: SectorRow[];
}

export default function SectorSummary({ sectors }: Props) {
  if (sectors.length === 0) return null;

  const maxAbs = Math.max(...sectors.map((s) => Math.abs(s.contribution)));

  return (
    <div className="rounded-lg border border-gray-200 bg-white p-4">
      <p className="mb-3 text-sm font-medium text-gray-900">Sector Attribution</p>
      <div className="space-y-2">
        {sectors.map((sector) => {
          const isGain = sector.contribution >= 0;
          const barWidth = maxAbs > 0 ? (Math.abs(sector.contribution) / maxAbs) * 100 : 0;
          const sign = isGain ? "+" : "";
          return (
            <div key={sector.sector} className="flex items-center gap-3 text-sm">
              {/* Sector name */}
              <span className="w-40 shrink-0 truncate text-gray-700">{sector.sector}</span>
              {/* Bar */}
              <div className="flex-1">
                <div
                  className={`h-4 rounded-sm ${isGain ? "bg-green-400" : "bg-red-400"}`}
                  style={{ width: `${barWidth}%`, minWidth: "2px" }}
                  role="progressbar"
                  aria-valuenow={Math.abs(barWidth)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${sector.sector} contribution`}
                />
              </div>
              {/* Value */}
              <span
                className={`w-20 shrink-0 text-right font-medium ${
                  isGain ? "text-green-600" : "text-red-600"
                }`}
              >
                {sign}
                {sector.contribution.toFixed(3)} pp
              </span>
              {/* Pct of move */}
              <span className="w-16 shrink-0 text-right text-gray-400">
                {Math.abs(sector.pct_of_total_move).toFixed(0)}%
              </span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
