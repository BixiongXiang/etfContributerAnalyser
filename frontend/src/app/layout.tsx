import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Who moved my ETFs?",
  description: "Market Attribution Dashboard — understand why your ETFs moved today.",
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
            Who moved my ETFs?
          </h1>
          <p className="mt-0.5 text-sm text-gray-400">
            Market Attribution Dashboard
          </p>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-8">{children}</main>
      </body>
    </html>
  );
}
