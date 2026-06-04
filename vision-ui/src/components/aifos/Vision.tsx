import { useEffect, useRef, useState } from "react";
import { api } from "@/lib/aifos/api";
import { useApi } from "@/lib/aifos/useFetch";
import { useWSEvents } from "@/lib/aifos/ws";
import { Chip } from "./Panel";
import { Mic, MicOff, Send, X, Sparkles, Volume2, VolumeX, Ear } from "lucide-react";
import { motion, AnimatePresence } from "framer-motion";

type Msg = { role: "user" | "assistant" | "system"; text: string };

export function VisionDock() {
  const { data: info } = useApi<{ name: string; engine: string }>("/api/assistant/info");
  const name = info?.name || "Vision";
  const engine = info?.engine || "—";

  const [open, setOpen] = useState(true);
  const [msgs, setMsgs] = useState<Msg[]>([
    { role: "system", text: `${name} online. Engine: ${engine}. I reason in probabilities — never guarantees.` },
  ]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [listening, setListening] = useState(false);
  const [wake, setWake] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const recogRef = useRef<any>(null);
  const wakeRef = useRef(false);
  const nameRef = useRef(name);
  useEffect(() => { wakeRef.current = wake; }, [wake]);
  useEffect(() => { nameRef.current = name; }, [name]);

  const speak = (text: string) => {
    if (typeof window === "undefined" || !window.speechSynthesis) return;
    window.speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(text);
    u.rate = 1.02; u.pitch = 1;
    u.onstart = () => setSpeaking(true);
    u.onend = () => setSpeaking(false);
    u.onerror = () => setSpeaking(false);
    window.speechSynthesis.speak(u);
  };
  const stopSpeak = () => { if (typeof window !== "undefined") window.speechSynthesis?.cancel(); setSpeaking(false); };

  const send = async (q: string) => {
    if (!q.trim()) return;
    stopSpeak();
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setInput("");
    setBusy(true);
    try {
      const r = await api<{ answer: string; engine?: string }>("/api/assistant/ask", { method: "POST", body: JSON.stringify({ question: q }) });
      setMsgs((m) => [...m, { role: "assistant", text: r.answer }]);
      speak(r.answer);
    } catch {
      setMsgs((m) => [...m, { role: "assistant", text: "I couldn't reach the backend. Falling back to silence." }]);
    } finally { setBusy(false); }
  };

  const getRecog = () => {
    if (typeof window === "undefined") return null;
    const SR = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SR) return null;
    const r = new SR(); r.lang = "en-US"; r.interimResults = false;
    return r;
  };

  const oneShot = () => {
    stopSpeak();
    const r = getRecog(); if (!r) { alert("Voice not supported in this browser."); return; }
    r.continuous = false;
    setListening(true);
    r.onresult = (e: any) => { const t = e.results[0]?.[0]?.transcript || ""; send(t); };
    r.onend = () => setListening(false);
    r.onerror = () => setListening(false);
    r.onspeechstart = () => stopSpeak();
    try { r.start(); } catch { setListening(false); }
  };

  // wake-word continuous
  useEffect(() => {
    if (!wake) { try { recogRef.current?.stop(); } catch {} recogRef.current = null; return; }
    const r = getRecog(); if (!r) { setWake(false); alert("Voice not supported."); return; }
    r.continuous = true; r.interimResults = true;
    r.onresult = (e: any) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (!e.results[i].isFinal) continue;
        const t = (e.results[i][0]?.transcript || "").toLowerCase();
        const n = nameRef.current.toLowerCase();
        const idx = t.indexOf(n);
        if (idx >= 0) {
          const q = t.slice(idx + n.length).replace(/^[\s,:.!?]+/, "").trim();
          if (q) send(q);
        }
      }
    };
    r.onspeechstart = () => { if (speaking) stopSpeak(); };
    r.onend = () => { if (wakeRef.current) { try { r.start(); } catch {} } };
    r.onerror = () => {};
    try { r.start(); } catch {}
    recogRef.current = r;
    return () => { try { r.stop(); } catch {} };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [wake]);

  // WS alerts spoken aloud
  useWSEvents((e: any) => {
    if (e.kind !== "control" && e.kind !== "fill") return;
    let text = "";
    if (e.kind === "control") text = `🔔 ${e.action || e.message || "control event"}`;
    if (e.kind === "fill") text = `🔔 Fill: ${e.symbol || ""} ${e.side || ""} ${e.qty ?? ""} @ ${e.price ?? ""}`;
    setMsgs((m) => [...m, { role: "system", text }]);
    speak(text.replace("🔔", ""));
  });

  return (
    <div className="fixed bottom-4 right-4 z-50">
      <AnimatePresence>
        {open && (
          <motion.div initial={{ opacity: 0, y: 12, scale: 0.96 }} animate={{ opacity: 1, y: 0, scale: 1 }} exit={{ opacity: 0, y: 12, scale: 0.96 }}
            className="glass w-[360px] max-w-[calc(100vw-2rem)] flex flex-col overflow-hidden shadow-2xl shadow-[color:var(--indigo)]/20">
            <header className="flex items-center justify-between px-3 py-2 border-b border-border">
              <div className="flex items-center gap-2">
                <div className="relative w-7 h-7 rounded-lg bg-gradient-to-br from-[color:var(--cyan)] to-[color:var(--indigo)] grid place-items-center">
                  <Sparkles className="w-3.5 h-3.5 text-background" />
                  {speaking && <span className="absolute -bottom-0.5 -right-0.5 w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />}
                </div>
                <div>
                  <div className="text-xs font-semibold">{name}</div>
                  <div className="text-[9px] text-muted-foreground">engine · {engine}</div>
                </div>
              </div>
              <div className="flex gap-1.5">
                <button onClick={() => setWake(!wake)} title="Wake-word toggle" className={`p-1.5 rounded-md border border-border ${wake ? "text-[color:var(--cyan)] bg-[color:var(--cyan)]/10" : "text-muted-foreground hover:text-foreground"}`}>
                  <Ear className="w-3.5 h-3.5" />
                </button>
                <button onClick={() => setOpen(false)} className="p-1.5 rounded-md border border-border text-muted-foreground hover:text-foreground"><X className="w-3.5 h-3.5" /></button>
              </div>
            </header>
            <div className="px-3 py-2 max-h-[50vh] min-h-[200px] overflow-auto space-y-2 text-[12px]">
              {msgs.map((m, i) => (
                <div key={i} className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}>
                  <div className={`whitespace-pre-wrap leading-snug px-2.5 py-1.5 rounded-lg max-w-[85%] ${
                    m.role === "user" ? "bg-[color:var(--cyan)]/15 border border-[color:var(--cyan)]/30" :
                    m.role === "assistant" ? "bg-secondary/50 border border-border" :
                    "text-[10px] text-muted-foreground italic"
                  }`}>{m.text}</div>
                </div>
              ))}
              {busy && <div className="text-[10px] text-muted-foreground animate-pulse">thinking…</div>}
            </div>
            {speaking && (
              <button onClick={stopSpeak} className="mx-3 mb-2 text-[10px] flex items-center gap-1.5 justify-center py-1 rounded-md bg-rose-500/15 border border-rose-500/40 text-rose-300 hover:bg-rose-500/25">
                <VolumeX className="w-3 h-3" /> Tap to stop speaking
              </button>
            )}
            <form onSubmit={(e) => { e.preventDefault(); send(input); }} className="p-2 border-t border-border flex gap-1.5">
              <button type="button" onClick={oneShot} className={`p-2 rounded-md border border-border ${listening ? "text-rose-300 bg-rose-500/15" : "text-muted-foreground hover:text-foreground"}`} title="Tap to speak">
                {listening ? <MicOff className="w-3.5 h-3.5" /> : <Mic className="w-3.5 h-3.5" />}
              </button>
              <input value={input} onChange={(e) => setInput(e.target.value)} placeholder={`Ask ${name}…`} className="flex-1 text-xs bg-secondary/60 border border-border rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-1 focus:ring-[color:var(--cyan)]/60" />
              <button type="submit" disabled={busy} className="px-2.5 rounded-md bg-gradient-to-r from-[color:var(--cyan)] to-[color:var(--indigo)] text-background"><Send className="w-3.5 h-3.5" /></button>
            </form>
          </motion.div>
        )}
      </AnimatePresence>

      {!open && (
        <button onClick={() => setOpen(true)} className="glass px-4 py-2.5 flex items-center gap-2 hover:scale-[1.02] transition">
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-[color:var(--cyan)] to-[color:var(--indigo)] grid place-items-center"><Sparkles className="w-3 h-3 text-background" /></div>
          <span className="text-xs font-semibold">{name}</span>
          {speaking ? <Volume2 className="w-3 h-3 text-emerald-400 animate-pulse" /> : <Chip tone="cyan">ask</Chip>}
        </button>
      )}
    </div>
  );
}
