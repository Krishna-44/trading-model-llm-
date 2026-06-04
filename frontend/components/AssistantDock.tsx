"use client";
import { useEffect, useRef, useState } from "react";

import { api } from "@/lib/api";

interface Msg { role: "user" | "bot"; text: string }

export function AssistantDock({ events = [] }: { events?: any[] }) {
  const [open, setOpen] = useState(true);
  const [name, setName] = useState("Vision");
  const [engine, setEngine] = useState("local");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [wake, setWake] = useState(false);
  const [speaking, setSpeaking] = useState(false);
  const [supported, setSupported] = useState(false);
  const recRef = useRef<any>(null);
  const wakeRef = useRef(false);
  const lastSeq = useRef<number>(-1);
  const bottomRef = useRef<HTMLDivElement>(null);

  // ── speech: speak + interrupt (barge-in) ──────────────────────────────
  const stopSpeaking = () => {
    try { window.speechSynthesis.cancel(); } catch { /* */ }
    setSpeaking(false);
  };
  const speak = (text: string) => {
    try {
      window.speechSynthesis.cancel();
      const u = new SpeechSynthesisUtterance(text.slice(0, 600));
      u.rate = 1.05;
      u.onstart = () => setSpeaking(true);
      u.onend = () => setSpeaking(false);
      u.onerror = () => setSpeaking(false);
      window.speechSynthesis.speak(u);
    } catch { /* no TTS */ }
  };

  useEffect(() => {
    api.assistantInfo().then((i) => {
      setName(i.name);
      setEngine(i.engine);
      setMsgs([{ role: "bot", text: `${i.name} online — running on-device. Ask "what's happening in the world", "how's my risk", or say "stop trading". Just say "${i.name}" to talk.` }]);
    }).catch(() => setMsgs([{ role: "bot", text: "Assistant online — ask me about the desk." }]));
    setSupported(typeof window !== "undefined" &&
      !!((window as any).SpeechRecognition || (window as any).webkitSpeechRecognition));
    return () => { try { window.speechSynthesis.cancel(); } catch { /* */ } };
  }, []);

  useEffect(() => { bottomRef.current?.scrollIntoView({ behavior: "smooth" }); }, [msgs]);

  // proactive spoken alerts: announce new fills / kill-switch / resume out loud
  useEffect(() => {
    if (!events.length) return;
    const newest = events[0].seq;
    if (lastSeq.current < 0) { lastSeq.current = newest; return; }
    const fresh = events.filter((e) => e.seq > lastSeq.current).reverse();
    lastSeq.current = newest;
    for (const e of fresh) {
      let line = "";
      if (e.kind === "control" && e.event === "kill") line = `Heads up sir — kill switch tripped. ${e.reason || ""}`;
      else if (e.kind === "control" && e.event === "resume") line = "Trading resumed.";
      else if (e.kind === "fill") line = `Order filled: ${e.fill?.side} ${e.symbol} at ${e.fill?.price}.`;
      if (line) { setMsgs((m) => [...m, { role: "bot", text: `🔔 ${line}` }]); speak(line); }
    }
  }, [events]);

  const send = async (text: string) => {
    const q = text.trim();
    if (!q || busy) return;
    stopSpeaking();
    setInput("");
    setMsgs((m) => [...m, { role: "user", text: q }]);
    setBusy(true);
    try {
      const r = await api.assistantAsk(q);
      setEngine(r.engine);
      setMsgs((m) => [...m, { role: "bot", text: r.answer }]);
      speak(r.answer);
    } catch {
      setMsgs((m) => [...m, { role: "bot", text: "I couldn't reach the desk just now." }]);
    } finally {
      setBusy(false);
    }
  };

  const newRec = () => {
    const R = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    const rec = new R();
    rec.lang = "en-US";
    rec.interimResults = false;
    return rec;
  };

  const micOnce = () => {
    if (!supported) return;
    stopSpeaking(); // pressing to talk interrupts Vision
    try {
      const rec = newRec();
      rec.continuous = false;
      rec.onspeechstart = () => stopSpeaking();
      rec.onresult = (e: any) => send(e.results[0][0].transcript);
      rec.start();
    } catch { /* mic denied */ }
  };

  const toggleWake = () => {
    if (!supported) return;
    if (wake) { wakeRef.current = false; setWake(false); recRef.current?.stop(); return; }
    const w = name.toLowerCase();
    wakeRef.current = true; setWake(true);
    const rec = newRec();
    rec.continuous = true;
    rec.onspeechstart = () => stopSpeaking(); // barge-in: you talk -> Vision stops
    rec.onresult = (e: any) => {
      for (let i = e.resultIndex; i < e.results.length; i++) {
        if (!e.results[i].isFinal) continue;
        const t = e.results[i][0].transcript.toLowerCase().trim();
        if (t.includes("stop") && speaking) { stopSpeaking(); continue; }
        if (t.includes(w)) {
          const q = t.split(w).pop()?.trim();
          send(q && q.length > 1 ? q : "what's happening in the world");
        }
      }
    };
    rec.onend = () => { if (wakeRef.current) try { rec.start(); } catch { /* */ } };
    recRef.current = rec;
    try { rec.start(); } catch { /* */ }
  };

  if (!open) {
    return (
      <button onClick={() => setOpen(true)}
        className="fixed bottom-5 right-5 z-50 grid h-12 w-12 place-items-center rounded-full border border-accent/40 bg-accent/15 text-accent-soft shadow-glow">
        <span className="num text-lg font-bold">Λ</span>
      </button>
    );
  }

  return (
    <div className="panel fixed bottom-5 right-5 z-50 flex h-[460px] w-[340px] flex-col overflow-hidden">
      <div className="flex items-center justify-between border-b border-white/[0.07] px-3 py-2">
        <div className="flex items-center gap-2">
          <span className={`h-2 w-2 rounded-full ${speaking ? "bg-accent animate-pulseGlow" : wake ? "bg-long animate-pulseGlow" : "bg-accent"}`} />
          <span className="text-sm font-semibold text-zinc-100">{name}</span>
          <span className="chip border-white/10 text-[9px] text-zinc-500">{engine}</span>
        </div>
        <button onClick={() => setOpen(false)} className="text-zinc-500 hover:text-zinc-200">✕</button>
      </div>

      <div className="flex-1 space-y-2 overflow-y-auto p-3">
        {msgs.map((m, i) => (
          <div key={i} className={`max-w-[88%] rounded-lg px-2.5 py-1.5 text-[12px] leading-snug ${
            m.role === "user" ? "ml-auto bg-accent/15 text-accent-soft" : "bg-white/[0.04] text-zinc-200"}`}>
            <span style={{ whiteSpace: "pre-wrap" }}>{m.text}</span>
          </div>
        ))}
        {busy && <div className="text-[11px] text-zinc-500">…thinking</div>}
        <div ref={bottomRef} />
      </div>

      {speaking && (
        <button onClick={stopSpeaking}
          className="mx-2 mb-1 flex items-center justify-center gap-2 rounded-lg border border-short/40 bg-short/10 py-1.5 text-xs font-medium text-short-soft transition hover:bg-short/20">
          <span className="animate-pulseGlow">⏹</span> Tap to stop speaking
        </button>
      )}

      <div className="flex items-center gap-1.5 border-t border-white/[0.07] p-2">
        <button title="speak once (interrupts Vision)" onClick={micOnce} disabled={!supported}
          className="btn px-2 disabled:opacity-30">🎤</button>
        <button title={`wake-word: say "${name}"`} onClick={toggleWake} disabled={!supported}
          className={`btn px-2 ${wake ? "btn-accent" : ""} disabled:opacity-30`}>{wake ? "◉" : "○"}</button>
        <input
          value={input} onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => e.key === "Enter" && send(input)}
          placeholder={`Ask ${name}…`}
          className="min-w-0 flex-1 rounded-lg border border-white/10 bg-ink-800 px-2.5 py-1.5 text-xs text-zinc-100 outline-none focus:border-accent/40"
        />
        <button onClick={() => send(input)} disabled={busy} className="btn btn-accent px-2.5">→</button>
      </div>
    </div>
  );
}
