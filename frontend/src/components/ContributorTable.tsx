/**
 * ContributorTable — renders top negative or top positive contributors.
 *
 * Columns: Rank | Ticker | Price | Weight | Return | Contribution | Sector
 */

import type { ContributorRow } from "@/lib/types";

interface Props {
  title: string;
  rows: ContributorRow[];
  variant: "positive" | "negative";
}

function fmt(n: number, decimals = 2): string {
  return (n >= 0 ? "+" : "") + n.toFixed(decimals) + "%";
}

function fmtContrib(n: number): string {
  return (n >= 0 ? "+" : "") + n.toFixed(3) + " pp";
}

function fmtPrice(p: number | null): string {
  if (p === null) return "—";
  return "$" + p.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

export default function ContributorTable({ title, rows, variant }: Props) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-gray-700 bg-[#161b22] p-4">
        <p className="text-sm font-medium text-gray-200">{title}</p>
        <p className="mt-2 text-sm text-gray-500">No data available.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-gray-700 bg-[#161b22]">
      <div className="border-b border-gray-700 px-4 py-3">
        <p className="text-sm font-medium text-gray-200">{title}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-700 bg-[#0d1117] text-left text-xs font-medium text-gray-500">
              <th className="px-4 py-2">#</th>
              <th className="px-4 py-2">Ticker</th>
              <th className="px-4 py-2 text-right">Price</th>
              <th className="px-4 py-2 text-right">Weight</th>
              <th className="px-4 py-2 text-right">Return</th>
              <th className="px-4 py-2 text-right">Contribution</th>
              <th className="px-4 py-2 hidden lg:table-cell">Sector</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isGain = row.contribution >= 0;
              const contribColor = isGain ? "text-green-400" : "text-red-400";
              const returnColor = row.return_pct >= 0 ? "text-green-400" : "text-red-400";
              return (
                <tr
                  key={row.symbol}
                  className="border-b border-gray-800 last:border-0 hover:bg-gray-800/40 transition-colors"
                >
                  <td className="px-4 py-2.5 text-gray-600">{i + 1}</td>
                  <td className="px-4 py-2.5 font-semibold text-white">{row.symbol}</td>
                  <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums">
                    {fmtPrice(row.price)}
                  </td>
                  <td className="px-4 py-2.5 text-right text-gray-400 tabular-nums">
                    {row.weight.toFixed(1)}%
                  </td>
                  <td className={`px-4 py-2.5 text-right tabular-nums ${returnColor}`}>
                    {fmt(row.return_pct)}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-medium tabular-nums ${contribColor}`}>
                    {fmtContrib(row.contribution)}
                  </td>
                  <td className="px-4 py-2.5 text-gray-500 hidden lg:table-cell">
                    {row.sector ?? "—"}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
