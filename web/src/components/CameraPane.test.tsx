import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { hostStatus } from "../test/fixtures";
import { CameraPane } from "./CameraPane";

afterEach(() => vi.useRealTimers());

describe("CameraPane", () => {
  it("shows the live stream when video is available", () => {
    render(<CameraPane host="bluey.local" slot={1} status={hostStatus("bluey.local", { has_video: true })} selected selectable={false} />);
    const img = screen.getByRole("img", { name: "Live feed from bluey.local" });
    expect(img.getAttribute("src")).toMatch(/^\/api\/cameras\/bluey.local\/mjpeg\?r=\d+$/);
    expect(screen.getByText("CAM 1")).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  it("retries the stream after an error", () => {
    vi.useFakeTimers();
    render(<CameraPane host="h" slot={1} status={hostStatus("h", { has_video: true })} selected selectable={false} />);
    const first = screen.getByRole("img").getAttribute("src");
    fireEvent.error(screen.getByRole("img"));
    act(() => {
      vi.advanceTimersByTime(1500);
    });
    expect(screen.getByRole("img").getAttribute("src")).not.toBe(first);
  });

  it("explains a missing signal versus a closed connection", () => {
    const { rerender } = render(
      <CameraPane host="h" slot={2} status={hostStatus("h")} selected={false} selectable={false} />,
    );
    expect(screen.getByText("No signal")).toBeInTheDocument();
    rerender(<CameraPane host="h" slot={2} status={hostStatus("h", { open: false })} selected={false} selectable={false} />);
    expect(screen.getByText("Not connected")).toBeInTheDocument();
    rerender(<CameraPane host="h" slot={null} status={undefined} selected={false} selectable={false} />);
    expect(screen.getByText("CAM")).toBeInTheDocument();
  });

  it("marks the selected pane and tracking state in two-screen", () => {
    const onSelect = vi.fn();
    render(
      <CameraPane
        host="h"
        slot={2}
        status={hostStatus("h", { auto_tracking: true, subjects: 3 })}
        selected
        selectable
        onSelect={onSelect}
      />,
    );
    const pane = screen.getByTestId("pane-h");
    expect(pane).toHaveClass("pane--selected", "pane--tracking", "pane--selectable");
    expect(screen.getByText("Controlling")).toBeInTheDocument();
    expect(screen.getByText(/Tracking · 3/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /control camera 2/i }));
    expect(onSelect).toHaveBeenCalled();
  });
});
