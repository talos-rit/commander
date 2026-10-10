import { afterEach, describe, expect, it, vi } from "vitest";
import { api, ApiError, mjpegUrl } from "./api";
import { errorResponse, mockApi } from "./test/fixtures";

afterEach(() => vi.unstubAllGlobals());

describe("api", () => {
  it("sends JSON bodies and parses responses", async () => {
    const { calls, fetchMock } = mockApi({ "POST /control/auto-track": { enabled: true } });
    await expect(api.setAutoTrack(true, "bluey.local")).resolves.toEqual({ enabled: true });
    expect(calls[0]).toEqual({
      method: "POST",
      path: "/control/auto-track",
      body: { enabled: true, host: "bluey.local" },
    });
    expect(fetchMock.mock.calls[0][1]?.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("omits the host for Home when none is given", async () => {
    const { calls } = mockApi({ "POST /control/home": { host: "a" } });
    await api.home();
    expect(calls[0].body).toEqual({});
  });

  it("encodes robot hosts in paths", async () => {
    const { calls } = mockApi({ "DELETE /robots/a%20b": undefined });
    await expect(api.deleteRobot("a b")).resolves.toBeUndefined();
    expect(calls[0].path).toBe("/robots/a%20b");
    expect(mjpegUrl("a b")).toBe("/api/cameras/a%20b/mjpeg");
  });

  it("turns FastAPI detail strings and lists into messages", async () => {
    mockApi({
      "GET /status": () => errorResponse(409, "Busy"),
      "GET /settings": () => errorResponse(422, [{ msg: "one" }, "two"]),
      "GET /robots": () => errorResponse(500, { odd: true }),
    });
    await expect(api.status()).rejects.toMatchObject({ message: "Busy", status: 409 });
    await expect(api.settings()).rejects.toMatchObject({ message: "one; two" });
    await expect(api.robots()).rejects.toMatchObject({ message: "Request failed" });
  });

  it("handles non-JSON error bodies", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("oops", { status: 502 })));
    await expect(api.status()).rejects.toMatchObject({ message: "Request failed", status: 502 });
  });

  it("reports an unreachable backend", async () => {
    vi.stubGlobal("fetch", vi.fn(() => Promise.reject(new TypeError("fail"))));
    const err = await api.status().catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(0);
  });
});
