export const pct = (x: number, digits = 1) =>
  `${(x * 100).toFixed(digits)}%`;

export function money(x: number, ccy = "INR"): string {
  const sign = x < 0 ? "-" : "";
  const abs = Math.abs(x);
  const sym = ccy === "INR" ? "₹" : ccy === "USD" ? "$" : "";
  if (abs >= 1e7) return `${sign}${sym}${(abs / 1e7).toFixed(2)}Cr`;
  if (abs >= 1e5) return `${sign}${sym}${(abs / 1e5).toFixed(2)}L`;
  return `${sign}${sym}${abs.toLocaleString("en-IN", { maximumFractionDigits: 0 })}`;
}

export const num = (x: number, d = 2) =>
  x?.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d }) ?? "—";

export const signColor = (x: number) =>
  x > 0 ? "text-long-soft" : x < 0 ? "text-short-soft" : "text-zinc-400";

export const stanceColor = (s: string) =>
  s === "bullish" ? "text-long-soft" : s === "bearish" ? "text-short-soft" : "text-zinc-400";

export const timeAgo = (iso: string): string => {
  const d = new Date(iso).getTime();
  const s = Math.max(0, Math.floor((Date.now() - d) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return `${Math.floor(s / 86400)}d ago`;
};
