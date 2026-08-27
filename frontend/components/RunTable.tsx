import Link from "next/link";
import type { Run } from "@/lib/api";
import { StatusBadge } from "@/components/StatusBadge";

function formatTime(iso: string | null): string {
  if (!iso) return "--";
  return new Date(iso).toLocaleString();
}

export function RunTable({ runs }: { runs: Run[] }) {
  if (runs.length === 0) {
    return (
      <p className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
        No runs yet -- submit a task above to start one.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-md border">
      <table className="w-full text-sm">
        <thead className="border-b bg-muted/40 text-left text-muted-foreground">
          <tr>
            <th className="px-4 py-2 font-medium">Prompt</th>
            <th className="px-4 py-2 font-medium">Status</th>
            <th className="px-4 py-2 font-medium">Started</th>
            <th className="px-4 py-2 font-medium">Cost</th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => (
            <tr key={run.id} className="border-b last:border-0 hover:bg-muted/30">
              <td className="max-w-md truncate px-4 py-2">
                <Link href={`/runs/${run.id}`} className="hover:underline">
                  {run.prompt}
                </Link>
              </td>
              <td className="px-4 py-2">
                <StatusBadge status={run.status} />
              </td>
              <td className="px-4 py-2 text-muted-foreground">{formatTime(run.created_at)}</td>
              <td className="px-4 py-2 text-muted-foreground">
                {run.cost_usd != null ? `$${run.cost_usd.toFixed(4)}` : "--"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
