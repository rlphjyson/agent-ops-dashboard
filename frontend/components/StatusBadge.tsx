import { Badge } from "@/components/ui/badge";
import type { RunStatus } from "@/lib/api";
import { cn } from "@/lib/utils";

const STATUS_STYLES: Record<RunStatus, string> = {
  queued: "",
  running: "bg-blue-600 text-white",
  completed: "bg-emerald-600 text-white",
  failed: "",
};

const STATUS_VARIANT: Record<RunStatus, "secondary" | "default" | "destructive"> = {
  queued: "secondary",
  running: "default",
  completed: "default",
  failed: "destructive",
};

export function StatusBadge({ status }: { status: RunStatus }) {
  return (
    <Badge variant={STATUS_VARIANT[status]} className={cn(STATUS_STYLES[status])}>
      {status}
    </Badge>
  );
}
