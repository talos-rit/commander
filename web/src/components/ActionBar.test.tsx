import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it, vi } from "vitest";
import { makeStatus } from "../test/fixtures";
import { ActionBar } from "./ActionBar";

afterEach(cleanup);

it("shows a compact robot error instead of a healthy linked indicator", () => {
  const status = makeStatus({ connections: { "bluey.local": {
    operator_connected: true,
    pi_vision: { enabled: false, perception_enabled: true, error: "IMPACT PROTECTION",
      robot_fault: "IMPACT PROTECTION", inference_s: .2, observation_age_s: .3, state: "FAULT" },
  } } });
  render(<ActionBar status={status} onHome={vi.fn()} onAutoTrack={vi.fn()} onVirtualCamera={vi.fn()} />);
  expect(screen.getByText("Robot error")).toHaveClass("chip--danger");
  expect(screen.getByText("Robot error")).toHaveAttribute("title", "IMPACT PROTECTION");
  expect(screen.queryByText("Robot linked")).not.toBeInTheDocument();
});
