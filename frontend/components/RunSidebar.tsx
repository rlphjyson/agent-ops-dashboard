"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, Plus, Trash2 } from "lucide-react";
import type { Run } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

interface RunSidebarProps {
  runs: Run[];
  loaded: boolean;
  onDelete: (runId: string) => void;
}

export function RunSidebar({ runs, loaded, onDelete }: RunSidebarProps) {
  const pathname = usePathname();

  function handleDeleteClick(event: React.MouseEvent, run: Run) {
    event.preventDefault();
    event.stopPropagation();
    if (window.confirm(`Delete "${run.prompt.slice(0, 60)}"? This can't be undone.`)) {
      onDelete(run.id);
    }
  }

  return (
    <aside className="flex h-full w-72 shrink-0 flex-col border-r bg-sidebar text-sidebar-foreground">
      <div className="flex items-center gap-2 px-4 py-4 text-sm font-semibold">
        <span className="flex size-7 items-center justify-center rounded-lg bg-primary text-primary-foreground">
          <Bot className="size-4" />
        </span>
        Agent Ops
      </div>
      <div className="px-3 pb-2">
        <Link
          href="/runs"
          className={cn(
            "flex items-center gap-2 rounded-md border border-sidebar-border px-3 py-2 text-sm font-medium transition-colors hover:bg-sidebar-accent",
            pathname === "/runs" && "bg-sidebar-accent",
          )}
        >
          <Plus className="size-4" />
          New task
        </Link>
      </div>
      <div className="flex-1 overflow-y-auto px-2 pb-3">
        {!loaded ? (
          <p className="px-2 py-4 text-xs text-sidebar-foreground/60">Loading...</p>
        ) : runs.length === 0 ? (
          <p className="px-2 py-4 text-xs text-sidebar-foreground/60">No runs yet.</p>
        ) : (
          <ul className="space-y-0.5">
            {runs.map((run) => {
              const active = pathname === `/runs/${run.id}`;
              return (
                <li key={run.id} className="group relative">
                  <Link
                    href={`/runs/${run.id}`}
                    className={cn(
                      "flex flex-col gap-1.5 rounded-md py-2 pr-8 pl-2.5 text-sm transition-colors hover:bg-sidebar-accent",
                      active && "bg-sidebar-accent",
                    )}
                  >
                    <span className="truncate">{run.prompt}</span>
                    <StatusBadge status={run.status} />
                  </Link>
                  <Button
                    variant="ghost"
                    size="icon"
                    aria-label="Delete conversation"
                    onClick={(event) => handleDeleteClick(event, run)}
                    className="absolute top-1/2 right-1 size-6 -translate-y-1/2 opacity-0 group-hover:opacity-100"
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </li>
              );
            })}
          </ul>
        )}
      </div>
    </aside>
  );
}
