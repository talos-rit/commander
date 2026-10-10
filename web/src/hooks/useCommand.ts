import { useCallback, useRef, useState } from "react";
import { ApiError } from "../api";

export interface Toast {
  id: number;
  message: string;
  tone: "error" | "info";
}

export function useToasts(timeoutMs = 4000) {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const nextId = useRef(1);

  const dismiss = useCallback((id: number) => {
    setToasts((current) => current.filter((toast) => toast.id !== id));
  }, []);

  const push = useCallback(
    (message: string, tone: Toast["tone"] = "error") => {
      const id = nextId.current++;
      setToasts((current) => [...current.filter((t) => t.message !== message), { id, message, tone }]);
      window.setTimeout(() => dismiss(id), timeoutMs);
    },
    [dismiss, timeoutMs],
  );

  return { toasts, push, dismiss };
}

/** Runs an API command, reports failures as toasts, then refreshes status. */
export function useCommand(push: (message: string) => void, refresh: () => Promise<void> | void) {
  return useCallback(
    async <T>(action: () => Promise<T>): Promise<T | undefined> => {
      try {
        return await action();
      } catch (err) {
        push(err instanceof ApiError ? err.message : "Command failed");
        return undefined;
      } finally {
        void refresh();
      }
    },
    [push, refresh],
  );
}
