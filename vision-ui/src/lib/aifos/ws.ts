import { useEffect, useRef, useState } from "react";
import { WS_URL } from "./api";

export type WSEvent =
  | { kind: "snapshot"; portfolio: any; risk: any }
  | { kind: "heartbeat"; portfolio: any; risk: any }
  | { kind: "decision"; seq: number; ts: number; [k: string]: any }
  | { kind: "fill"; seq: number; ts: number; [k: string]: any }
  | { kind: "control"; seq: number; ts: number; [k: string]: any };

type Listener = (e: WSEvent) => void;

let socket: WebSocket | null = null;
let listeners = new Set<Listener>();
let portfolio: any = null;
let risk: any = null;
let connected = false;
let backoff = 1000;
let stateListeners = new Set<() => void>();

function emit(e: WSEvent) { listeners.forEach((l) => l(e)); }
function notifyState() { stateListeners.forEach((l) => l()); }

function connect() {
  if (typeof window === "undefined") return;
  try {
    socket = new WebSocket(WS_URL);
    socket.onopen = () => { connected = true; backoff = 1000; notifyState(); };
    socket.onclose = () => {
      connected = false; socket = null; notifyState();
      setTimeout(connect, backoff);
      backoff = Math.min(backoff * 1.6, 15000);
    };
    socket.onerror = () => { try { socket?.close(); } catch {} };
    socket.onmessage = (ev) => {
      try {
        const msg: WSEvent = JSON.parse(ev.data);
        if (msg.kind === "snapshot" || msg.kind === "heartbeat") {
          portfolio = msg.portfolio; risk = msg.risk; notifyState();
        }
        emit(msg);
      } catch {}
    };
  } catch {
    setTimeout(connect, backoff);
  }
}

export function useWS() {
  const [, force] = useState(0);
  useEffect(() => {
    if (!socket) connect();
    const l = () => force((n) => n + 1);
    stateListeners.add(l);
    return () => { stateListeners.delete(l); };
  }, []);
  return { connected, portfolio, risk };
}

export function useWSEvents(handler: Listener) {
  const ref = useRef(handler);
  ref.current = handler;
  useEffect(() => {
    if (!socket) connect();
    const l: Listener = (e) => ref.current(e);
    listeners.add(l);
    return () => { listeners.delete(l); };
  }, []);
}
