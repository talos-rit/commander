import { act, renderHook } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../api";
import { useCommand, useToasts } from "./useCommand";

afterEach(() => vi.useRealTimers());

describe("useToasts", () => {
  it("adds, de-duplicates and expires toasts", () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useToasts(1000));
    act(() => {
      result.current.push("a");
      result.current.push("a");
      result.current.push("b", "info");
    });
    expect(result.current.toasts.map((t) => [t.message, t.tone])).toEqual([
      ["a", "error"],
      ["b", "info"],
    ]);
    act(() => result.current.dismiss(result.current.toasts[0].id));
    expect(result.current.toasts).toHaveLength(1);
    act(() => {
      vi.advanceTimersByTime(1000);
    });
    expect(result.current.toasts).toHaveLength(0);
  });
});

describe("useCommand", () => {
  it("returns results and refreshes", async () => {
    const push = vi.fn();
    const refresh = vi.fn();
    const { result } = renderHook(() => useCommand(push, refresh));
    await expect(result.current(async () => 5)).resolves.toBe(5);
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(push).not.toHaveBeenCalled();
  });

  it("reports API errors and generic failures", async () => {
    const push = vi.fn();
    const refresh = vi.fn();
    const { result } = renderHook(() => useCommand(push, refresh));
    await expect(result.current(() => Promise.reject(new ApiError("nope", 400)))).resolves.toBeUndefined();
    await result.current(() => Promise.reject(new Error("x")));
    expect(push.mock.calls).toEqual([["nope"], ["Command failed"]]);
    expect(refresh).toHaveBeenCalledTimes(2);
  });
});
