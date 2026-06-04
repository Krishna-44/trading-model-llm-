import { useEffect, useRef, useState } from "react";
import { api } from "./api";

export function useApi<T = any>(path: string | null, opts?: { pollMs?: number; deps?: any[] }) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<Error | null>(null);
  const [loading, setLoading] = useState<boolean>(!!path);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    if (!path) { setData(null); setLoading(false); return; }
    let cancelled = false;
    let timer: any;
    const run = async () => {
      try {
        const json = await api<T>(path);
        if (!cancelled && mounted.current) { setData(json); setError(null); }
      } catch (e: any) {
        if (!cancelled && mounted.current) setError(e);
      } finally {
        if (!cancelled && mounted.current) setLoading(false);
      }
      if (opts?.pollMs && !cancelled) timer = setTimeout(run, opts.pollMs);
    };
    setLoading(true);
    run();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [path, ...(opts?.deps || [])]);

  return { data, error, loading, refetch: () => path && api<T>(path).then(setData).catch(setError) };
}
