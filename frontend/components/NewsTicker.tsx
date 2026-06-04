"use client";
const short = (s: string) => s.replace(".NS", "").replace("-USD", "").replace("=X", "").replace("^", "");

export function NewsTicker({ items }: { items: any[] }) {
  if (!items || items.length === 0) return null;
  const doubled = [...items, ...items]; // seamless loop
  return (
    <div className="overflow-hidden border-y border-white/[0.06] bg-white/[0.02]">
      <div className="flex w-max animate-marquee gap-8 whitespace-nowrap py-1.5">
        {doubled.map((it, i) => (
          <span key={i} className="flex items-center gap-2 text-xs">
            <span className={`h-1.5 w-1.5 rounded-full ${it.sentiment === "bullish" ? "bg-long" : it.sentiment === "bearish" ? "bg-short" : "bg-zinc-500"}`} />
            <span className="num font-medium text-zinc-400">{short(it.symbol)}</span>
            <span className="text-zinc-300">{it.title}</span>
          </span>
        ))}
      </div>
    </div>
  );
}
