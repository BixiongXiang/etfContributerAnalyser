/**
 * ContributorTable — renders top negative or top positive contributors.
 *
 * Columns: Rank | Ticker | Weight | Return | Contribution | Sector
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

export default function ContributorTable({ title, rows, variant }: Props) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-gray-200 bg-white p-4">
        <p className="text-sm font-medium text-gray-700">{title}</p>
        <p className="mt-2 text-sm text-gray-400">No data available.</p>
      </div>
    );
  }

  return (
    <div className="overflow-hidden rounded-lg border border-gray-200 bg-white">
      <div className="border-b border-gray-100 px-4 py-3">
        <p className="text-sm font-medium text-gray-900">{title}</p>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 bg-gray-50 text-left text-xs font-medium text-gray-500">
              <th className="px-4 py-2">#</th>
              <th className="px-4 py-2">Ticker</th>
              <th className="px-4 py-2 text-right">Weight</th>
              <th className="px-4 py-2 text-right">Return</th>
              <th className="px-4 py-2 text-right">Contribution</th>
              <th className="px-4 py-2">Sector</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => {
              const isGain = row.contribution >= 0;
              const contribColor = isGain ? "text-green-600" : "text-red-600";
              return (
                <tr
                  key={row.symbol}
                  className="border-b border-gray-50 last:border-0 hover:bg-gray-50"
                >
                  <td className="px-4 py-2.5 text-gray-400">{i + 1}</td>
                  <td className="px-4 py-2.5 font-semibold">{row.symbol}</td>
                  <td className="px-4 py-2.5 text-right text-gray-600">
                    {row.weight.toFixed(1)}%
                  </td>
                  <td
                    className={`px-4 py-2.5 text-right ${
                      row.return_pct >= 0 ? "text-green-600" : "text-red-600"
                    }`}
                  >
                    {fmt(row.return_pct)}
                  </td>
                  <td className={`px-4 py-2.5 text-right font-medium ${contribColor}`}>
                    {fmtContrib(row.contribution)}
                  </td>
                  <td className="px-4 py-2.5 text-gray-500">
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
