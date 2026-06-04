import { cn } from "@/lib/utils";
import type { ReactNode } from "react";

export function Panel({ title, subtitle, right, children, className, padded = true }: {
  title?: ReactNode;
  subtitle?: ReactNode;
  right?: ReactNode;
  children?: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section className={cn("glass overflow-hidden flex flex-col", className)}>
      {(title || right) && (
        <header className="flex items-center justify-between px-4 pt-3 pb-2 border-b border-border/60">
          <div className="min-w-0">
            {title && <h3 className="text-xs font-semibold uppercase tracking-wider text-foreground/90">{title}</h3>}
            {subtitle && <p className="text-[10px] text-muted-foreground mt-0.5 truncate">{subtitle}</p>}
          </div>
          {right && <div className="flex items-center gap-2 shrink-0">{right}</div>}
        </header>
      )}
      <div className={cn("flex-1 min-h-0", padded && "p-4")}>{children}</div>
    </section>
  );
}

export function Chip({ children, tone = "default", className }: {
  children: ReactNode;
  tone?: "default" | "up" | "down" | "cyan" | "indigo" | "warn";
  className?: string;
}) {
  const tones: Record<string, string> = {
    default: "text-foreground/80",
    up: "text-[color:var(--up)] border-[color:var(--up)]/30 bg-[color:var(--up)]/10",
    down: "text-[color:var(--down)] border-[color:var(--down)]/30 bg-[color:var(--down)]/10",
    cyan: "text-[color:var(--cyan)] border-[color:var(--cyan)]/30 bg-[color:var(--cyan)]/10",
    indigo: "text-[color:var(--indigo)] border-[color:var(--indigo)]/30 bg-[color:var(--indigo)]/10",
    warn: "text-amber-300 border-amber-400/30 bg-amber-400/10",
  };
  return <span className={cn("chip", tones[tone], className)}>{children}</span>;
}

export function Dot({ on, color = "emerald" }: { on?: boolean; color?: "emerald" | "rose" | "amber" | "cyan" }) {
  const map = {
    emerald: on ? "text-emerald-400" : "text-muted-foreground/40",
    rose: "text-rose-400",
    amber: "text-amber-400",
    cyan: "text-cyan-400",
  };
  return (
    <span className={cn("relative inline-block w-2 h-2 rounded-full bg-current", map[color], on && "dot-pulse")} />
  );
}

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-md bg-white/5", className)} />;
}

export function Empty({ children = "No data" }: { children?: ReactNode }) {
  return <div className="text-xs text-muted-foreground/70 italic p-2">{children}</div>;
}
