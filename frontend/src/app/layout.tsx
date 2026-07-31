import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Market Attribution Dashboard",
  description: "Understand why an ETF moved today — ranked by each holding's contribution.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-gray-50 text-gray-900 antialiased">
        <header className="border-b border-gray-200 bg-white px-6 py-4">
          <h1 className="text-xl font-semibold tracking-tight">
            Market Attribution Dashboard
          </h1>
          <p className="mt-0.5 text-sm text-gray-500">
            Why did the ETF move today?
          </p>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
