import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { makeStatus } from "../test/fixtures";
import { ActionBar, CommandReceipt, commandReceiptChip } from "./ActionBar";

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

describe("command receipt", () => {
  const receipt = {
    sent: 1,
    acked: 1,
    last_command: "Home",
    last_sent_age_s: 0.2,
    last_ack_age_s: 0.1,
    last_failed: false,
  };

  it("shows Operator's queue receipt without claiming the arm finished", () => {
    const status = makeStatus({ connections: { "bluey.local": { command: receipt } } });
    render(<ActionBar status={status} onHome={vi.fn()} onAutoTrack={vi.fn()} onVirtualCamera={vi.fn()} />);
    expect(screen.queryByText("Home · Received")).not.toBeInTheDocument();
    cleanup();
    render(<CommandReceipt status={status} />);
    const chip = screen.getByRole("status");
    expect(chip).toHaveTextContent("Home · Received");
    expect(chip).toHaveClass("receipt-toast");
    expect(chip).toHaveAttribute("title", expect.stringMatching(/queued/i));
    expect(chip).toHaveAttribute("title", expect.stringMatching(/still be moving/i));
  });

  it("says when the frame was written and Operator has not answered yet", () => {
    expect(commandReceiptChip({ ...receipt, acked: 0, last_ack_age_s: null, last_sent_age_s: 0.2 })?.text).toBe("Home · Waiting");
    expect(commandReceiptChip({ ...receipt, acked: 0, last_ack_age_s: null, last_sent_age_s: 2 })?.text).toBe("Home · No receipt");
  });

  it("says the Pi accepted a command when that link cannot see an ACK", () => {
    expect(commandReceiptChip({ ...receipt, acked: null })?.text).toBe("Home · Sent");
  });

  it("hides a receipt once it is no longer news", () => {
    expect(commandReceiptChip({ ...receipt, last_ack_age_s: 10, last_sent_age_s: 10 })).toBeNull();
    expect(commandReceiptChip(null)).toBeNull();
  });
});
