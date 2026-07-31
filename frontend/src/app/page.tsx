/**
 * Homepage — renders the ETF attribution dashboard.
 *
 * All data fetching is done client-side inside ETFDashboard so the
 * Next.js rewrite proxy (localhost:3000/api → localhost:8888/api) is used,
 * which works reliably in the browser during local development.
 */

import ETFDashboard from "@/components/ETFDashboard";

export default function HomePage() {
  return <ETFDashboard etfs={[]} />;
}
