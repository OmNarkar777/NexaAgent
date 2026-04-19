import { useEffect, useRef, useCallback } from "react";
export function useSSE(url, onMessage, enabled = true) {
  const esRef = useRef(null);
  const close = useCallback(() => { esRef.current?.close(); esRef.current = null; }, []);
  useEffect(() => {
    if (!enabled || !url) return;
    const token = localStorage.getItem("nexaagent_token");
    const es = new EventSource(token ? `${url}?token=${token}` : url);
    esRef.current = es;
    es.onmessage = (e) => { try { onMessage(JSON.parse(e.data)); } catch { onMessage(e.data); } };
    return close;
  }, [url, enabled, close]);
  return close;
}