import { act, cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { CenteringTolerance } from "./CenteringTolerance";

afterEach(() => { cleanup(); vi.useRealTimers(); });

it("applies the latest slider value while dragging without flooding requests", async () => {
  vi.useFakeTimers();
  const onChange = vi.fn().mockResolvedValue({ acceptable_ratio: .12 });
  const view = render(<CenteringTolerance ratio={.25} onChange={onChange} />);
  const slider = screen.getByRole("slider", { name: "Centering tolerance" });
  fireEvent.change(slider, { target: { value: "15" } });
  fireEvent.change(slider, { target: { value: "12" } });
  expect(screen.getByText("12%")).toBeInTheDocument();
  expect(onChange).not.toHaveBeenCalled();
  await act(async () => { await vi.advanceTimersByTimeAsync(250); });
  expect(onChange).toHaveBeenCalledExactlyOnceWith(.12);
  view.rerender(<CenteringTolerance ratio={.12} onChange={onChange} />);
  expect(slider).toHaveValue("12");
});

it("cancels pending tuning when the selected robot's control is removed", async () => {
  vi.useFakeTimers();
  const onChange = vi.fn().mockResolvedValue({});
  const view = render(<CenteringTolerance ratio={.25} onChange={onChange} />);
  fireEvent.change(screen.getByRole("slider"), { target: { value: "10" } });
  view.unmount();
  await act(async () => { await vi.advanceTimersByTimeAsync(250); });
  expect(onChange).not.toHaveBeenCalled();
});
