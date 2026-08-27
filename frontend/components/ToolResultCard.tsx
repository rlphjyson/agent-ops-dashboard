import { CheckCircle2, XCircle } from "lucide-react";
import type { ToolResultPayload } from "@/lib/api";
import { cn } from "@/lib/utils";

function formatContent(content: unknown): string {
  if (typeof content === "string") return content;
  return JSON.stringify(content, null, 2);
}

export function ToolResultCard({ payload }: { payload: ToolResultPayload }) {
  return (
    <div
      className={cn(
        "rounded-md border p-3 text-sm",
        payload.is_error
          ? "border-destructive/40 bg-destructive/5"
          : "border-emerald-200 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/40",
      )}
    >
      <div
        className={cn(
          "mb-1 flex items-center gap-2 font-medium",
          payload.is_error ? "text-destructive" : "text-emerald-900 dark:text-emerald-200",
        )}
      >
        {payload.is_error ? <XCircle className="size-4" /> : <CheckCircle2 className="size-4" />}
        {payload.is_error ? "Tool error" : "Tool result"}
      </div>
      <pre className="overflow-x-auto text-xs whitespace-pre-wrap">
        {formatContent(payload.content)}
      </pre>
    </div>
  );
}
