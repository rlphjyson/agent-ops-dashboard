import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { EventTimeline } from "./EventTimeline";
import type { RunEvent } from "@/lib/api";

describe("EventTimeline", () => {
  it("shows a waiting message when there are no events yet", () => {
    render(<EventTimeline events={[]} />);
    expect(screen.getByText(/waiting for the agent/i)).toBeInTheDocument();
  });

  it("renders one card per event, dispatched by kind", () => {
    const events: RunEvent[] = [
      { id: 1, run_id: "r1", kind: "system", payload: { tools: ["a", "b"] }, created_at: "2026-01-01T00:00:00Z" },
      { id: 2, run_id: "r1", kind: "assistant_text", payload: { text: "Looking into it." }, created_at: "2026-01-01T00:00:01Z" },
      {
        id: 3,
        run_id: "r1",
        kind: "tool_use",
        payload: { tool_use_id: "t1", name: "mcp__kb__search_notes", input: { query: "x" } },
        created_at: "2026-01-01T00:00:02Z",
      },
      {
        id: 4,
        run_id: "r1",
        kind: "tool_result",
        payload: { tool_use_id: "t1", content: { found: true }, is_error: false },
        created_at: "2026-01-01T00:00:03Z",
      },
      {
        id: 5,
        run_id: "r1",
        kind: "result",
        payload: { is_error: false, result_text: "All done.", cost_usd: 0.02, num_turns: 2 },
        created_at: "2026-01-01T00:00:04Z",
      },
    ];

    render(<EventTimeline events={events} />);

    expect(screen.getByText(/2 tools available/i)).toBeInTheDocument();
    expect(screen.getByText("Looking into it.")).toBeInTheDocument();
    expect(screen.getByText("mcp__kb__search_notes")).toBeInTheDocument();
    expect(screen.getByText(/tool result/i)).toBeInTheDocument();
    expect(screen.getByText(/run completed/i)).toBeInTheDocument();
    expect(screen.getByText("All done.")).toBeInTheDocument();
  });

  it("renders an error event", () => {
    const events: RunEvent[] = [
      {
        id: 1,
        run_id: "r1",
        kind: "error",
        payload: { message: "mcp-toolkit-ai checkout not found" },
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    render(<EventTimeline events={events} />);
    expect(screen.getByText(/checkout not found/i)).toBeInTheDocument();
  });

  it("renders a follow-up user_text event", () => {
    const events: RunEvent[] = [
      {
        id: 1,
        run_id: "r1",
        kind: "user_text",
        payload: { text: "Now check the other file too." },
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    render(<EventTimeline events={events} />);
    expect(screen.getByText("Now check the other file too.")).toBeInTheDocument();
  });

  it("renders a cancelled event", () => {
    const events: RunEvent[] = [
      {
        id: 1,
        run_id: "r1",
        kind: "cancelled",
        payload: { message: "Stopped by user." },
        created_at: "2026-01-01T00:00:00Z",
      },
    ];
    render(<EventTimeline events={events} />);
    expect(screen.getByText("Stopped by user.")).toBeInTheDocument();
  });
});
