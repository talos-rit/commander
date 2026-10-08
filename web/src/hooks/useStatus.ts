import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api";
import type { Status } from "../types";

export const STATUS_POLL_MS = 400;

export function useStatus(intervalMs = STATUS_POLL_MS) {
  const [status, setStatus] = useState<Status | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const inFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try {
      setStatus(await api.status());
      setError(null);
      setStarting(false);
    } catch (err) {
      if (err instanceof ApiError && err.starting) {
        setStarting(true);
        setError(null);
      } else {
        setStarting(false);
        setError(err instanceof ApiError ? err.message : "Lost contact with Commander");
      }
    } finally {
      inFlight.current = false;
    }
  }, []);

  useEffect(() => {
    void refresh();
    const id = window.setInterval(() => void refresh(), intervalMs);
    return () => window.clearInterval(id);
  }, [refresh, intervalMs]);

  return { status, error, starting, refresh, setStatus };
}
