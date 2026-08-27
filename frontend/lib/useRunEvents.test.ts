import { describe, expect, it, afterEach, beforeEach, vi } from "vitest";
import { renderHook, waitFor, act } from "@testing-library/react";
import { useRunEvents } from "./useRunEvents";
import { FakeWebSocket, installFakeWebSocket } from "./testing/fakeWebSocket";

describe("useRunEvents", () => {
  beforeEach(() => {
    installFakeWebSocket();
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("does not connect when there is no token", () => {
    renderHook(() => useRunEvents(null));
    expect(FakeWebSocket.instances).toHaveLength(0);
  });

  it("connects to the unfiltered fleet URL when no runId is given", () => {
    renderHook(() => useRunEvents("tok"));
    expect(FakeWebSocket.instances).toHaveLength(1);
    const url = new URL(FakeWebSocket.instances[0].url, "ws://x");
    expect(url.searchParams.get("token")).toBe("tok");
    expect(url.searchParams.has("run_id")).toBe(false);
  });

  it("includes run_id in the URL when filtering to one run", () => {
    renderHook(() => useRunEvents("tok", "run-1"));
    const url = new URL(FakeWebSocket.instances[0].url, "ws://x");
    expect(url.searchParams.get("run_id")).toBe("run-1");
  });

  it("accumulates events received over the socket, in order", async () => {
    const { result } = renderHook(() => useRunEvents("tok", "run-1"));
    const socket = FakeWebSocket.instances[0];

    act(() => socket.simulateOpen());
    act(() =>
      socket.simulateMessage({
        id: 1,
        run_id: "run-1",
        kind: "assistant_text",
        payload: { text: "hi" },
        created_at: "2026-01-01T00:00:00Z",
      }),
    );
    act(() =>
      socket.simulateMessage({
        id: 2,
        run_id: "run-1",
        kind: "result",
        payload: { is_error: false, result_text: "done", cost_usd: 0.01, num_turns: 1 },
        created_at: "2026-01-01T00:00:01Z",
      }),
    );

    await waitFor(() => expect(result.current.events).toHaveLength(2));
    expect(result.current.events.map((e) => e.id)).toEqual([1, 2]);
  });

  it("dedupes an event id received more than once (e.g. re-backfilled after a reconnect)", async () => {
    const { result } = renderHook(() => useRunEvents("tok", "run-1"));
    const socket = FakeWebSocket.instances[0];
    const event = {
      id: 1,
      run_id: "run-1",
      kind: "assistant_text",
      payload: { text: "hi" },
      created_at: "2026-01-01T00:00:00Z",
    };

    act(() => socket.simulateOpen());
    act(() => socket.simulateMessage(event));
    act(() => socket.simulateMessage(event));

    await waitFor(() => expect(result.current.events).toHaveLength(1));
  });

  it("reports connected state as the socket opens and closes", async () => {
    const { result } = renderHook(() => useRunEvents("tok"));
    expect(result.current.connected).toBe(false);

    act(() => FakeWebSocket.instances[0].simulateOpen());
    await waitFor(() => expect(result.current.connected).toBe(true));

    act(() => FakeWebSocket.instances[0].simulateClose());
    await waitFor(() => expect(result.current.connected).toBe(false));
  });

  it("reconnects after a close without wiping already-accumulated events", async () => {
    vi.useFakeTimers();
    const { result } = renderHook(() => useRunEvents("tok"));

    act(() => FakeWebSocket.instances[0].simulateOpen());
    act(() =>
      FakeWebSocket.instances[0].simulateMessage({
        id: 1,
        run_id: "run-1",
        kind: "assistant_text",
        payload: { text: "before reconnect" },
        created_at: "2026-01-01T00:00:00Z",
      }),
    );
    expect(result.current.events).toHaveLength(1);

    act(() => FakeWebSocket.instances[0].simulateClose());
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500);
    });

    expect(FakeWebSocket.instances.length).toBeGreaterThan(1);
    act(() => FakeWebSocket.instances[FakeWebSocket.instances.length - 1].simulateOpen());

    // The fleet view never backfills, so a reconnect must not discard what was already seen.
    expect(result.current.events).toHaveLength(1);
    vi.useRealTimers();
  });
});
