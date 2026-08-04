/**
 * SectorSummary — horizontal bar chart of sector contributions.
 *
 * Mobile: stacks sector name + values vertically, bar spans full width.
 * Desktop: single-row layout with name | bar | value | pct.
 */

import type { SectorRow } from "@/lib/types";

interface Props {
  sectors: SectorRow[];
}

export default function SectorSummary({ sectors }: Props) {
  if (sectors.length === 0) return null;

  const maxAbs = Math.max(...sectors.map((s) => Math.abs(s.contribution)));

  return (
    <div className="rounded-lg border border-gray-700 bg-[#161b22] p-4">
      <p className="mb-3 text-sm font-medium text-gray-200">Sector Attribution</p>
      <div className="space-y-3">
        {sectors.map((sector) => {
          const isGain = sector.contribution >= 0;
          const barWidth = maxAbs > 0 ? (Math.abs(sector.contribution) / maxAbs) * 100 : 0;
          const sign = isGain ? "+" : "";
          const valueColor = isGain ? "text-green-400" : "text-red-400";
          const barColor = isGain ? "bg-green-500" : "bg-red-500";

          return (
            <div key={sector.sector}>
              {/* Top row: name + values */}
              <div className="mb-1 flex items-center justify-between gap-2 text-sm">
                <span className="truncate text-gray-300">{sector.sector}</span>
                <div className="flex shrink-0 items-center gap-3">
                  <span className={`font-medium ${valueColor}`}>
                    {sign}{sector.contribution.toFixed(3)} pp
                  </span>
                  <span className="text-gray-500 text-xs">
                    {Math.abs(sector.pct_of_total_move).toFixed(0)}%
                  </span>
                </div>
              </div>
              {/* Bar — full width on all screen sizes */}
              <div className="h-2 w-full overflow-hidden rounded-full bg-gray-700">
                <div
                  className={`h-full rounded-full ${barColor}`}
                  style={{ width: `${barWidth}%`, minWidth: "2px" }}
                  role="progressbar"
                  aria-valuenow={Math.abs(barWidth)}
                  aria-valuemin={0}
                  aria-valuemax={100}
                  aria-label={`${sector.sector} contribution`}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
