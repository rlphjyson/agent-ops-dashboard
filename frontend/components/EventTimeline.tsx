"use client";

import { useEffect, useRef } from "react";
import { AlertTriangle, OctagonX } from "lucide-react";
import type { RunEvent } from "@/lib/api";
import { ToolCallCard } from "@/components/ToolCallCard";
import { ToolResultCard } from "@/components/ToolResultCard";
import { ResultBanner } from "@/components/ResultBanner";
import { SystemToolsRow } from "@/components/SystemToolsRow";

function EventRow({ event }: { event: RunEvent }) {
  switch (event.kind) {
    case "system":
      return <SystemToolsRow payload={event.payload} />;
    case "assistant_text":
      return (
        <div className="max-w-2xl rounded-md bg-muted/60 p-3 text-sm whitespace-pre-wrap">
          {event.payload.text}
        </div>
      );
    case "user_text":
      return (
        <div className="ml-auto max-w-2xl rounded-md bg-primary/10 p-3 text-sm whitespace-pre-wrap">
          {event.payload.text}
        </div>
      );
    case "tool_use":
      return <ToolCallCard payload={event.payload} />;
    case "tool_result":
      return <ToolResultCard payload={event.payload} />;
    case "result":
      return <ResultBanner payload={event.payload} />;
    case "error":
      return (
        <div className="flex items-center gap-2 rounded-md border border-destructive/40 bg-destructive/5 p-3 text-sm text-destructive">
          <AlertTriangle className="size-4 shrink-0" />
          {event.payload.message}
        </div>
      );
    case "cancelled":
      return (
        <div className="flex items-center gap-2 rounded-md border border-muted-foreground/30 bg-muted/40 p-3 text-sm text-muted-foreground">
          <OctagonX className="size-4 shrink-0" />
          {event.payload.message}
        </div>
      );
  }
}

export function EventTimeline({ events }: { events: RunEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // Optional chaining on the method itself, not just the ref: jsdom (used by the test
    // environment) doesn't implement scrollIntoView at all.
    bottomRef.current?.scrollIntoView?.({ behavior: "smooth", block: "end" });
  }, [events.length]);

  if (events.length === 0) {
    return <p className="text-sm text-muted-foreground">Waiting for the agent to start...</p>;
  }

  return (
    <div className="space-y-3">
      {events.map((event) => (
        <EventRow key={event.id} event={event} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
