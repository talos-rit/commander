import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

// jsdom has no WebGL. ArmTwin.test.tsx overrides this with a prop-recording stub.
vi.mock("../components/ArmScene", () => ({ default: () => null }));

afterEach(() => {
  cleanup();
});
