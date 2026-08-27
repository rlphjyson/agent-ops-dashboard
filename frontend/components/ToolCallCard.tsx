import { Wrench } from "lucide-react";
import type { ToolUsePayload } from "@/lib/api";

export function ToolCallCard({ payload }: { payload: ToolUsePayload }) {
  return (
    <div className="rounded-md border border-blue-200 bg-blue-50 p-3 text-sm dark:border-blue-900 dark:bg-blue-950/40">
      <div className="mb-1 flex items-center gap-2 font-medium text-blue-900 dark:text-blue-200">
        <Wrench className="size-4" />
        {payload.name}
      </div>
      <pre className="overflow-x-auto text-xs text-blue-950/80 dark:text-blue-100/80">
        {JSON.stringify(payload.input, null, 2)}
      </pre>
    </div>
  );
}
