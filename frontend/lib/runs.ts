import type { Run, RunEvent } from "@/lib/api";

/** Pure derivation of a run's live status/result from the latest relevant event -- used by both
 * the fleet page (all runs) and the run-detail page (one run) so their "merge live WS events
 * into REST-fetched state" logic doesn't diverge. Deliberately a plain function computed via
 * useMemo at the call site, not something a separate effect writes into state: the merged view
 * is a pure function of (run, events), so it doesn't need its own copy kept in sync by an effect. */
export function applyLatestEventToRun(run: Run, events: RunEvent[]): Run {
  const relevant = events.filter((e) => e.run_id === run.id);
  const latest = relevant[relevant.length - 1];
  if (!latest) return run;

  if (latest.kind === "result") {
    return {
      ...run,
      status: latest.payload.is_error ? "failed" : "completed",
      result_text: latest.payload.result_text,
      cost_usd: latest.payload.cost_usd,
      num_turns: latest.payload.num_turns,
    };
  }
  if (latest.kind === "error") {
    return { ...run, status: "failed", error_message: latest.payload.message };
  }
  if (latest.kind === "cancelled") {
    return { ...run, status: "cancelled" };
  }
  return run.status === "queued" ? { ...run, status: "running" } : run;
}
