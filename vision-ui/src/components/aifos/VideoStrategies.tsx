import { useState } from "react";
import { useApi } from "@/lib/aifos/useFetch";
import { api } from "@/lib/aifos/api";
import { Panel, Chip, Empty } from "./Panel";

const tone = (s: string) =>
  s === "done" ? "up" : s === "error" ? "down" : s === "processing" ? "cyan" : "warn";

const short = (u: string) =>
  u.replace(/^https?:\/\/(www\.)?/, "").replace(/^youtube\.com\/watch\?v=/, "yt:").slice(0, 64);

/** Video → Strategy queue. Paste a link → it becomes a row. n8n polls this table
 *  (GET /videos/queued), extracts the strategy, and writes the result back
 *  (POST /videos/{id}/result). The row walks queued → processing → done. */
export function VideoStrategies() {
  const { data, refetch } = useApi<any>("/api/strategies/videos", { pollMs: 6000 });
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);
  const videos: any[] = data?.videos || [];

  const submit = async () => {
    const u = url.trim();
    if (!u || busy) return;
    setBusy(true);
    try {
      await api("/api/strategies/videos", { method: "POST", body: JSON.stringify({ url: u }) });
      setUrl("");
      refetch();
    } catch {} finally { setBusy(false); }
  };

  const counts = videos.reduce((a: any, v: any) => ((a[v.status] = (a[v.status] || 0) + 1), a), {});

  return (
    <Panel
      title="Video → Strategy"
      subtitle="paste a link · n8n extracts → maps → backtests → review"
      right={videos.length ? (
        <span className="text-[10px] text-muted-foreground num">
          {counts.queued || 0} queued · {counts.processing || 0} processing · {counts.done || 0} done
        </span>
      ) : null}
    >
      <div className="flex gap-2 mb-3">
        <input
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") submit(); }}
          placeholder="https://youtube.com/watch?v=…  (strategy / educational video)"
          className="flex-1 bg-secondary/30 border border-border rounded px-2.5 py-1.5 text-[12px] outline-none focus:border-[color:var(--cyan)]/50"
        />
        <button
          onClick={submit}
          disabled={busy || !url.trim()}
          className="chip border-[color:var(--cyan)]/40 text-[color:var(--cyan)] bg-[color:var(--cyan)]/10 disabled:opacity-40 px-3"
        >
          {busy ? "adding…" : "+ add"}
        </button>
      </div>

      {videos.length === 0 ? (
        <Empty>no videos yet — paste a strategy video link to queue it for extraction</Empty>
      ) : (
        <div className="overflow-hidden rounded-md border border-border">
          <table className="w-full text-[11px]">
            <thead>
              <tr className="bg-secondary/30 text-muted-foreground text-[9px] uppercase tracking-wide">
                <th className="text-left font-medium px-2 py-1.5 w-[88px]">Status</th>
                <th className="text-left font-medium px-2 py-1.5">Video</th>
                <th className="text-left font-medium px-2 py-1.5">Result</th>
              </tr>
            </thead>
            <tbody>
              {videos.map((v: any) => (
                <tr key={v.id} className="border-t border-border/50">
                  <td className="px-2 py-1.5 align-top"><Chip tone={tone(v.status)}>{v.status}</Chip></td>
                  <td className="px-2 py-1.5 align-top">
                    <a href={v.url} target="_blank" rel="noreferrer"
                       className="text-foreground/90 hover:text-[color:var(--cyan)] truncate block max-w-[420px]"
                       title={v.url}>
                      {v.title || short(v.url)}
                    </a>
                  </td>
                  <td className="px-2 py-1.5 align-top text-muted-foreground">
                    {v.status === "done" ? v.note
                      : v.status === "error" ? <span className="text-[color:var(--down)]">{v.note || "failed"}</span>
                      : v.status === "processing" ? "extracting…"
                      : "waiting for n8n"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <p className="text-[10px] text-muted-foreground/70 italic mt-3">
        n8n polls this queue, extracts the educational strategy logic, maps it to a tested
        template and backtests it — then writes the result back here. Nothing auto-deploys; the
        extracted strategy lands in the marketplace inbox for your review.
      </p>
    </Panel>
  );
}
