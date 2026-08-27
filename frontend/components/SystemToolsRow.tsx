"use client";

import { useState } from "react";
import { ChevronDown, ChevronRight, Info } from "lucide-react";
import type { SystemPayload } from "@/lib/api";

export function SystemToolsRow({ payload }: { payload: SystemPayload }) {
  const [expanded, setExpanded] = useState(false);
  const count = payload.tools.length;

  return (
    <div className="text-xs text-muted-foreground">
      <button
        type="button"
        onClick={() => setExpanded((prev) => !prev)}
        className="flex items-center gap-2 rounded hover:text-foreground"
      >
        {expanded ? <ChevronDown className="size-3.5" /> : <ChevronRight className="size-3.5" />}
        <Info className="size-3.5" />
        {count} tool{count === 1 ? "" : "s"} available
      </button>
      {expanded && (
        <ul className="mt-2 ml-5 flex flex-wrap gap-1.5">
          {payload.tools.map((tool) => (
            <li
              key={tool}
              className="rounded-md border border-border bg-muted/40 px-2 py-0.5 font-mono text-[0.7rem]"
            >
              {tool}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
