import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { HostStatus } from "../types";
import { ZoomPanel } from "./ZoomPanel";

afterEach(cleanup);

function host(overrides: Partial<HostStatus> = {}): HostStatus {
  return {
    host: "bluey.local",
    slot: 1,
    configured: true,
    open: true,
    manual_only: false,
    operator_connected: true,
    has_video: true,
    auto_tracking: false,
    telemetry: null,
    subject_list: [
      { id: 2, confidence: 0.91, box: [10, 20, 50, 120] },
      { id: 5, confidence: 0.6, box: [200, 40, 230, 100] },
    ],
    zoom: { target: null, locked: false, holding: false, level: 1, fill: 0.6 },
    ...overrides,
  };
}

it("lists subjects and picks one to zoom on", () => {
  const onTarget = vi.fn();
  render(<ZoomPanel host={host()} modelLoaded onTarget={onTarget} onFill={vi.fn()} />);

  expect(screen.getByRole("radio", { name: /Full frame/ })).toBeChecked();
  expect(screen.getByRole("radio", { name: /Subject #2/ })).toHaveTextContent("91% · 40×100");
  fireEvent.click(screen.getByRole("radio", { name: /Subject #5/ }));

  expect(onTarget).toHaveBeenCalledExactlyOnceWith(5);
});

it("shows the followed subject and returns to full frame", () => {
  const onTarget = vi.fn();
  const zoom = { target: 2, locked: true, holding: false, level: 2.4, fill: 0.6 };
  render(<ZoomPanel host={host({ zoom })} modelLoaded onTarget={onTarget} onFill={vi.fn()} />);

  expect(screen.getByText(/Following #2 · 2\.4×/)).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /Subject #2/ })).toBeChecked();
  fireEvent.click(screen.getByRole("radio", { name: /Full frame/ }));

  expect(onTarget).toHaveBeenCalledExactlyOnceWith(null);
});

it("keeps a lost target visible in the list", () => {
  const zoom = { target: 9, locked: false, holding: true, level: 2, fill: 0.6 };
  render(<ZoomPanel host={host({ zoom })} modelLoaded onTarget={vi.fn()} onFill={vi.fn()} />);

  expect(screen.getByText(/#9 lost · holding/)).toBeInTheDocument();
  expect(screen.getByRole("radio", { name: /Subject #9.*out of view/ })).toBeDisabled();
});

it("commits the fill slider on release", () => {
  const onFill = vi.fn();
  render(<ZoomPanel host={host()} modelLoaded onTarget={vi.fn()} onFill={onFill} />);
  const slider = screen.getByRole("slider", { name: "Subject fill" });

  fireEvent.change(slider, { target: { value: "80" } });
  expect(onFill).not.toHaveBeenCalled();
  fireEvent.pointerUp(slider);

  expect(onFill).toHaveBeenCalledExactlyOnceWith(0.8);
});

it("explains why zoom is unavailable", () => {
  const { rerender } = render(
    <ZoomPanel host={host({ subject_list: [] })} modelLoaded={false} onTarget={vi.fn()} onFill={vi.fn()} />,
  );
  expect(screen.getByText(/Load a detection model/)).toBeInTheDocument();

  rerender(<ZoomPanel host={host({ zoom: null })} modelLoaded onTarget={vi.fn()} onFill={vi.fn()} />);
  expect(screen.queryByRole("radiogroup")).not.toBeInTheDocument();
});

it("says PiVision keeps choosing who the arm follows", () => {
  const { rerender } = render(
    <ZoomPanel host={host()} modelLoaded={false} piVision onTarget={vi.fn()} onFill={vi.fn()} />,
  );
  expect(screen.getByText(/Turn on PiVision perception/)).toBeInTheDocument();

  rerender(<ZoomPanel host={host()} modelLoaded piVision onTarget={vi.fn()} onFill={vi.fn()} />);
  expect(screen.getByRole("radio", { name: /Subject #2/ })).toBeInTheDocument();
  expect(screen.getByText(/PiVision still picks who the arm follows/)).toBeInTheDocument();
});
