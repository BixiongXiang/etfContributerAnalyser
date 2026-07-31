/**
 * Homepage — ETF selector + attribution dashboard.
 *
 * For now renders a placeholder until the attribution API endpoints
 * are implemented in the backend (Week 2 of the implementation plan).
 */

import { fetchETFs } from "@/lib/api";
import ETFDashboard from "@/components/ETFDashboard";

export const revalidate = 60; // ISR: revalidate page every 60 seconds

export default async function HomePage() {
  let etfs: Awaited<ReturnType<typeof fetchETFs>> = [];
  let error: string | null = null;

  try {
    etfs = await fetchETFs();
  } catch (e) {
    error = "Backend is not yet available. Start the FastAPI server to see live data.";
  }

  return (
    <div>
      {error ? (
        <div className="rounded-lg border border-yellow-300 bg-yellow-50 px-4 py-3 text-sm text-yellow-800">
          {error}
        </div>
      ) : (
        <ETFDashboard etfs={etfs} />
      )}
    </div>
  );
}
