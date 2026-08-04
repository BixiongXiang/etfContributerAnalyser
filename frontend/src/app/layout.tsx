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
      <body className="min-h-screen bg-[#0f1117] text-gray-100 antialiased">
        <header className="border-b border-gray-700 bg-[#161b22] px-6 py-4">
          <h1 className="text-xl font-semibold tracking-tight text-white">
            Market Attribution Dashboard
          </h1>
          <p className="mt-0.5 text-sm text-gray-400">
            Why did the ETF move today?
          </p>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
