import { CircleCheck, CircleX } from "lucide-react";
import type { ResultPayload } from "@/lib/api";
import { cn } from "@/lib/utils";

export function ResultBanner({ payload }: { payload: ResultPayload }) {
  return (
    <div
      className={cn(
        "rounded-md border p-4",
        payload.is_error
          ? "border-destructive/40 bg-destructive/5"
          : "border-emerald-200 bg-emerald-50 dark:border-emerald-900 dark:bg-emerald-950/40",
      )}
    >
      <div
        className={cn(
          "mb-2 flex items-center gap-2 font-semibold",
          payload.is_error ? "text-destructive" : "text-emerald-900 dark:text-emerald-200",
        )}
      >
        {payload.is_error ? <CircleX className="size-5" /> : <CircleCheck className="size-5" />}
        {payload.is_error ? "Run failed" : "Run completed"}
      </div>
      <p className="text-sm whitespace-pre-wrap">{payload.result_text}</p>
      <div className="mt-3 flex gap-4 text-xs text-muted-foreground">
        {payload.cost_usd != null && <span>Cost: ${payload.cost_usd.toFixed(4)}</span>}
        {payload.num_turns != null && <span>Turns: {payload.num_turns}</span>}
      </div>
    </div>
  );
}
