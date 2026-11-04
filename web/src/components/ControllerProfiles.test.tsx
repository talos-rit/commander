import { render, screen } from "@testing-library/react";
import { DebugRail } from "./DebugRail";
import { makeStatus } from "../test/fixtures";
import type { ControllerStatus } from "../types";

function renderProfile(controller: ControllerStatus) {
  return render(<DebugRail status={makeStatus({ connections: { "bluey.local": { controller } } })}
    onMoveStart={vi.fn()} onMoveStop={vi.fn()} onCartesianStart={vi.fn()} onCartesianStop={vi.fn()}
    onJointStart={vi.fn()} onJointStop={vi.fn()} onStop={vi.fn()} onEnableControl={vi.fn()}
    onSpeed={vi.fn()} onJogMode={vi.fn()} onModel={vi.fn()} onHome={vi.fn()} onZoomTarget={vi.fn()} onZoomFill={vi.fn()}
    onRecognitionLeniency={vi.fn()} onForgetSubjects={vi.fn()} />);
}
it("shows only supported manual controls for the ESP demo", () => {
  renderProfile({ configured: "esp-one-axis", reported: "esp-one-axis", state: "verified" });
  expect(screen.getByRole("button", { name: "Jog left" })).toBeEnabled();
  expect(screen.getByRole("button", { name: "Jog up" })).toBeDisabled();
  expect(screen.queryByText("Cartesian")).not.toBeInTheDocument();
  expect(screen.queryByRole("slider", { name: "Manual speed" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Enable control" })).toBeDisabled();
});
it("blocks movement on mismatch and keeps Stop available", () => {
  renderProfile({ configured: "native", reported: "esp-one-axis", state: "mismatch" });
  expect(screen.getByRole("button", { name: "Jog left" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Home" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Stop" })).toBeEnabled();
});
