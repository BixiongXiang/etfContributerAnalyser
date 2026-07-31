/**
 * DataFreshnessTag — shows when data was last updated.
 * Turns yellow if data is older than 1 business day.
 */

interface Props {
  isoTimestamp: string;
}

export default function DataFreshnessTag({ isoTimestamp }: Props) {
  const dt = new Date(isoTimestamp);
  const now = new Date();
  const ageMs = now.getTime() - dt.getTime();
  const ageHours = ageMs / 1000 / 60 / 60;

  // Stale if > 28 hours (covers overnight + next trading day)
  const isStale = ageHours > 28;

  const formatted = dt.toLocaleString("en-US", {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });

  return (
    <span
      className={`rounded px-2 py-1 text-xs font-medium ${
        isStale
          ? "bg-yellow-100 text-yellow-800"
          : "bg-gray-100 text-gray-600"
      }`}
      title={isoTimestamp}
    >
      {isStale ? "⚠ Stale — " : ""}Updated: {formatted}
    </span>
  );
}
