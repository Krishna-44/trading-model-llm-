"use client";
import { useEffect, useRef, useState } from "react";

import { WS_URL } from "./api";
import type { Portfolio, RiskSnapshot } from "./types";

export interface WSState {
  connected: boolean;
  portfolio?: Portfolio;
  risk?: RiskSnapshot;
  events: any[];
}

export function useAifosSocket(): WSState {
  const [state, setState] = useState<WSState>({ connected: false, events: [] });
  const ref = useRef<WebSocket | null>(null);

  useEffect(() => {
    let stopped = false;
    let retry: ReturnType<typeof setTimeout>;

    const connect = () => {
      let ws: WebSocket;
      try {
        ws = new WebSocket(WS_URL);
      } catch {
        retry = setTimeout(connect, 2500);
        return;
      }
      ref.current = ws;
      ws.onopen = () => setState((s) => ({ ...s, connected: true }));
      ws.onclose = () => {
        setState((s) => ({ ...s, connected: false }));
        if (!stopped) retry = setTimeout(connect, 2500);
      };
      ws.onerror = () => ws.close();
      ws.onmessage = (e) => {
        const msg = JSON.parse(e.data);
        setState((s) => {
          const next: WSState = { ...s };
          if (msg.portfolio) next.portfolio = msg.portfolio;
          if (msg.risk) next.risk = msg.risk;
          if (["decision", "fill", "control"].includes(msg.kind))
            next.events = [msg, ...s.events].slice(0, 40);
          return next;
        });
      };
    };

    connect();
    return () => {
      stopped = true;
      clearTimeout(retry);
      ref.current?.close();
    };
  }, []);

  return state;
}
