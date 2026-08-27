import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { SystemToolsRow } from "./SystemToolsRow";

describe("SystemToolsRow", () => {
  it("starts collapsed, hiding the tool names", () => {
    render(<SystemToolsRow payload={{ tools: ["mcp__kb__search_notes", "mcp__devenv__run_repo_tests"] }} />);
    expect(screen.getByText(/2 tools available/i)).toBeInTheDocument();
    expect(screen.queryByText("mcp__kb__search_notes")).not.toBeInTheDocument();
  });

  it("expands to show every tool name on click, and collapses again on a second click", async () => {
    const user = userEvent.setup();
    render(<SystemToolsRow payload={{ tools: ["mcp__kb__search_notes", "mcp__devenv__run_repo_tests"] }} />);

    await user.click(screen.getByText(/2 tools available/i));
    expect(screen.getByText("mcp__kb__search_notes")).toBeInTheDocument();
    expect(screen.getByText("mcp__devenv__run_repo_tests")).toBeInTheDocument();

    await user.click(screen.getByText(/2 tools available/i));
    expect(screen.queryByText("mcp__kb__search_notes")).not.toBeInTheDocument();
  });

  it("uses singular phrasing for exactly one tool", () => {
    render(<SystemToolsRow payload={{ tools: ["mcp__kb__search_notes"] }} />);
    expect(screen.getByText(/1 tool available/i)).toBeInTheDocument();
  });
});
