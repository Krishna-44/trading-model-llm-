import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AIFOS — Autonomous Financial Operating System",
  description: "Probability-gated, multi-agent autonomous trading research platform.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen grid-bg">{children}</body>
    </html>
  );
}
