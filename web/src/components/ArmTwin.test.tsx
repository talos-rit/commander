import { render, screen } from "@testing-library/react";
import { ArmTwin } from "./ArmTwin";
import { hostStatus } from "../test/fixtures";
import { armPoints, linkPoses } from "../armKinematics";

// jsdom has no WebGL; record what the scene would draw instead.
vi.mock("./ArmScene", () => ({
  default: ({ positions, dimmed }: { positions: Record<string, number> | null; dimmed: boolean }) =>
    <div data-testid="scene" data-pose={positions ? "yes" : "no"} data-dimmed={String(dimmed)} />,
}));

const positions = { base_joint: 0, shoulder_joint: -Math.PI / 2, elbow_joint: 0, pitch_joint: 0 };
const telemetry = { encoder_counts: null, encoder_age_s: null, joint_counts: [0, 1088, 2113, 1151, 0], joint_age_s: 0.2, joint_positions: positions };

it("uses the URDF's 220 mm links and straight vertical reference", () => {
  const p = armPoints(positions);
  expect(p.elbow_joint[2] - p.shoulder_joint[2]).toBeCloseTo(0.22, 6);
  expect(p.pitch_joint[2] - p.elbow_joint[2]).toBeCloseTo(0.22, 6);
  expect(p.pitch_joint[1]).toBeCloseTo(p.shoulder_joint[1], 6);
});

it("places every CAD link frame along the chain", () => {
  const links = linkPoses(positions);
  expect(Object.keys(links)).toEqual(["base_Link", "shoulder_Link", "elbow_Link", "pitch_Link", "roll_Link", "gripper_Link", "pad1_Link", "pad2_Link"]);
  expect(links.pitch_Link.p).toEqual(armPoints(positions).elbow_joint);
});

it("does not invent a home pose from raw encoders or a connection", () => {
  render(<ArmTwin host={hostStatus("a", { telemetry: { ...telemetry, joint_positions: null } })} />);
  expect(screen.getByText("No measured pose")).toBeInTheDocument();
  expect(screen.getByText("Waiting for joint telemetry")).toBeInTheDocument();
});

it("shows live pose, marks stale feedback, and hides disconnected cached state", async () => {
  const { rerender } = render(<ArmTwin host={hostStatus("a", { telemetry })} />);
  expect(screen.getByText("Live telemetry")).toBeInTheDocument();
  expect(screen.queryByText("No measured pose")).not.toBeInTheDocument();
  expect(await screen.findByTestId("scene")).toHaveAttribute("data-pose", "yes");
  rerender(<ArmTwin host={hostStatus("a", { telemetry: { ...telemetry, joint_age_s: 2 } })} />);
  expect(screen.getByText("Stale telemetry")).toBeInTheDocument();
  expect(screen.getByTestId("scene")).toHaveAttribute("data-dimmed", "true");
  rerender(<ArmTwin host={hostStatus("b", { telemetry, operator_connected: false })} />);
  expect(screen.getByText("Disconnected")).toBeInTheDocument();
  expect(screen.getByText("No measured pose")).toBeInTheDocument();
  expect(screen.getByTestId("scene")).toHaveAttribute("data-pose", "no");
});
