import { describe, expect, it, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RunComposer } from "./RunComposer";
import { ApiError, type Run } from "@/lib/api";

const { sendMessage, cancelRun } = vi.hoisted(() => ({
  sendMessage: vi.fn(),
  cancelRun: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return { ...actual, sendMessage, cancelRun };
});

const BASE_RUN: Run = {
  id: "r1",
  prompt: "do it",
  status: "completed",
  result_text: "done",
  error_message: null,
  cost_usd: 0.01,
  num_turns: 1,
  created_at: "2026-01-01T00:00:00Z",
  started_at: "2026-01-01T00:00:00Z",
  completed_at: "2026-01-01T00:00:01Z",
};

describe("RunComposer", () => {
  beforeEach(() => {
    sendMessage.mockReset();
    cancelRun.mockReset();
  });

  it("shows a chat input, not a Stop button, once a run has settled", () => {
    render(<RunComposer token="t" run={BASE_RUN} onOptimisticUpdate={vi.fn()} />);
    expect(screen.getByPlaceholderText(/continue the conversation/i)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /stop/i })).not.toBeInTheDocument();
  });

  it("shows a Stop button, not a chat input, while a run is in progress", () => {
    render(<RunComposer token="t" run={{ ...BASE_RUN, status: "running" }} onOptimisticUpdate={vi.fn()} />);
    expect(screen.getByRole("button", { name: /stop/i })).toBeInTheDocument();
    expect(screen.queryByPlaceholderText(/continue the conversation/i)).not.toBeInTheDocument();
  });

  it("sends the typed prompt and optimistically marks the run running", async () => {
    sendMessage.mockResolvedValue({ ...BASE_RUN, status: "running" });
    const onOptimisticUpdate = vi.fn();
    const user = userEvent.setup();

    render(<RunComposer token="t" run={BASE_RUN} onOptimisticUpdate={onOptimisticUpdate} />);
    await user.type(screen.getByPlaceholderText(/continue the conversation/i), "one more thing");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(sendMessage).toHaveBeenCalledWith("t", "r1", "one more thing");
    expect(onOptimisticUpdate).toHaveBeenCalledWith({ status: "running" });
  });

  it("shows the API error message when sending fails", async () => {
    sendMessage.mockRejectedValue(new ApiError("This run has no resumable session to continue yet.", 400));
    const user = userEvent.setup();

    render(<RunComposer token="t" run={BASE_RUN} onOptimisticUpdate={vi.fn()} />);
    await user.type(screen.getByPlaceholderText(/continue the conversation/i), "hi again");
    await user.click(screen.getByRole("button", { name: /send/i }));

    expect(await screen.findByText(/no resumable session/i)).toBeInTheDocument();
  });

  it("calls cancelRun when Stop is clicked", async () => {
    cancelRun.mockResolvedValue({ ...BASE_RUN, status: "cancelled" });
    const user = userEvent.setup();

    render(<RunComposer token="t" run={{ ...BASE_RUN, status: "running" }} onOptimisticUpdate={vi.fn()} />);
    await user.click(screen.getByRole("button", { name: /stop/i }));

    expect(cancelRun).toHaveBeenCalledWith("t", "r1");
  });
});
