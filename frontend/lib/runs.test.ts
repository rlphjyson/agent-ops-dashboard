import { describe, expect, it } from "vitest";
import { applyLatestEventToRun } from "./runs";
import type { Run, RunEvent } from "./api";

const BASE_RUN: Run = {
  id: "r1",
  prompt: "do it",
  status: "queued",
  result_text: null,
  error_message: null,
  cost_usd: null,
  num_turns: null,
  created_at: "2026-01-01T00:00:00Z",
  started_at: null,
  completed_at: null,
};

function event(overrides: Partial<RunEvent>): RunEvent {
  return {
    id: 1,
    run_id: "r1",
    kind: "assistant_text",
    payload: { text: "x" },
    created_at: "2026-01-01T00:00:00Z",
    ...overrides,
  } as RunEvent;
}

describe("applyLatestEventToRun", () => {
  it("returns the run unchanged when there are no events for it", () => {
    expect(applyLatestEventToRun(BASE_RUN, [])).toEqual(BASE_RUN);
  });

  it("ignores events belonging to a different run", () => {
    const other = event({ run_id: "r2", kind: "result", payload: { is_error: false, result_text: "x", cost_usd: 0, num_turns: 1 } });
    expect(applyLatestEventToRun(BASE_RUN, [other])).toEqual(BASE_RUN);
  });

  it("flips status to running on the first relevant event if still queued", () => {
    const result = applyLatestEventToRun(BASE_RUN, [event({ kind: "assistant_text", payload: { text: "thinking" } })]);
    expect(result.status).toBe("running");
  });

  it("applies a successful result event", () => {
    const result = applyLatestEventToRun(BASE_RUN, [
      event({
        kind: "result",
        payload: { is_error: false, result_text: "all done", cost_usd: 0.05, num_turns: 3 },
      }),
    ]);
    expect(result.status).toBe("completed");
    expect(result.result_text).toBe("all done");
    expect(result.cost_usd).toBe(0.05);
    expect(result.num_turns).toBe(3);
  });

  it("applies a failing result event", () => {
    const result = applyLatestEventToRun(BASE_RUN, [
      event({
        kind: "result",
        payload: { is_error: true, result_text: "oops", cost_usd: 0.01, num_turns: 1 },
      }),
    ]);
    expect(result.status).toBe("failed");
  });

  it("applies an error event", () => {
    const result = applyLatestEventToRun(BASE_RUN, [
      event({ kind: "error", payload: { message: "toolkit not found" } }),
    ]);
    expect(result.status).toBe("failed");
    expect(result.error_message).toBe("toolkit not found");
  });

  it("uses only the latest relevant event, not an earlier one", () => {
    const result = applyLatestEventToRun(BASE_RUN, [
      event({ id: 1, kind: "assistant_text", payload: { text: "thinking" } }),
      event({
        id: 2,
        kind: "result",
        payload: { is_error: false, result_text: "done", cost_usd: 0, num_turns: 1 },
      }),
    ]);
    expect(result.status).toBe("completed");
  });
});
