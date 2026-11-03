import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import type { RecognitionStatus, ZoomStatus } from "../types";
import { RecognitionPanel } from "./RecognitionPanel";

afterEach(cleanup);

const recognition = (overrides: Partial<RecognitionStatus> = {}): RecognitionStatus => ({
  known: 3,
  appearance: true,
  faces: true,
  leniency: 0.5,
  ...overrides,
});

const zoom = (overrides: Partial<ZoomStatus> = {}): ZoomStatus => ({
  target: null,
  locked: false,
  holding: false,
  level: 1,
  fill: 0.6,
  ...overrides,
});

function panel(props: Partial<Parameters<typeof RecognitionPanel>[0]> = {}) {
  const onLeniency = vi.fn();
  const onForget = vi.fn();
  render(
    <RecognitionPanel recognition={recognition()} zoom={zoom()} onLeniency={onLeniency} onForget={onForget} {...props} />,
  );
  return { onLeniency, onForget };
}

it("shows what it matches with and how many people it knows", () => {
  panel();

  expect(screen.getByText(/Face \+ body/)).toBeInTheDocument();
  expect(screen.getByText("3")).toBeInTheDocument();
  expect(screen.getByText("Balanced")).toBeInTheDocument();
});

it("falls back to position when no model is running", () => {
  panel({ recognition: recognition({ appearance: false, faces: false }) });

  expect(screen.getByText(/Position only/)).toBeInTheDocument();
});

it("commits the leniency slider on release", () => {
  const { onLeniency } = panel();
  const slider = screen.getByRole("slider", { name: "Recognition leniency" });

  fireEvent.change(slider, { target: { value: "80" } });
  expect(screen.getByText("Lenient")).toBeInTheDocument();
  expect(onLeniency).not.toHaveBeenCalled();
  fireEvent.pointerUp(slider);

  expect(onLeniency).toHaveBeenCalledExactlyOnceWith(0.8);
});

it("forgets everyone, but only when someone is known", () => {
  const { onForget } = panel();
  fireEvent.click(screen.getByRole("button", { name: "Forget everyone" }));
  expect(onForget).toHaveBeenCalledOnce();

  cleanup();
  panel({ recognition: recognition({ known: 0 }) });
  expect(screen.getByRole("button", { name: "Forget everyone" })).toBeDisabled();
});

it("says how the zoom target was last recognized", () => {
  panel({ zoom: zoom({ target: 2, match: { by: "face", score: 0.91 } }) });
  expect(screen.getByText("#2 last recognized by face · 0.91")).toBeInTheDocument();

  cleanup();
  panel({ zoom: zoom({ target: 2 }) });
  expect(screen.getByText("#2 not recognized on a return yet")).toBeInTheDocument();
});

it("explains when the backend does not report recognition", () => {
  panel({ recognition: undefined });

  expect(screen.getByText(/does not report recognition/)).toBeInTheDocument();
  expect(screen.queryByRole("slider")).not.toBeInTheDocument();
});
