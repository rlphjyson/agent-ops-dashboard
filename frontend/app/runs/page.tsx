"use client";

import { useEffect, useMemo, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { listRuns, type Run } from "@/lib/api";
import { useRunEvents } from "@/lib/useRunEvents";
import { applyLatestEventToRun } from "@/lib/runs";
import { NavBar } from "@/components/NavBar";
import { RunForm } from "@/components/RunForm";
import { RunTable } from "@/components/RunTable";

export default function RunsPage() {
  const { token } = useRequireAuth();
  const [runs, setRuns] = useState<Run[]>([]);
  const [loaded, setLoaded] = useState(false);
  const { events } = useRunEvents(token);

  useEffect(() => {
    if (!token) return;
    listRuns(token).then((fetched) => {
      setRuns(fetched);
      setLoaded(true);
    });
  }, [token]);

  // Derived, not stored: the fleet list with live status applied is a pure function of the
  // REST-fetched runs plus the WS event stream, so it's computed at render time rather than
  // kept as its own state a separate effect writes into. Runs created elsewhere after this page
  // loaded aren't picked up until the next full load -- the WS's fleet view deliberately doesn't
  // backfill full history (see backend).
  const mergedRuns = useMemo(
    () => runs.map((run) => applyLatestEventToRun(run, events)),
    [runs, events],
  );

  if (!token) return null;

  return (
    <div className="flex min-h-screen flex-col">
      <NavBar />
      <main className="mx-auto w-full max-w-4xl flex-1 space-y-6 px-6 py-8">
        <RunForm />
        <div>
          <h2 className="mb-3 text-sm font-semibold text-muted-foreground">Runs</h2>
          {loaded && <RunTable runs={mergedRuns} />}
        </div>
      </main>
    </div>
  );
}
