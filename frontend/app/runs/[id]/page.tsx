"use client";

import { use, useEffect, useMemo, useState } from "react";
import { useRequireAuth } from "@/lib/auth";
import { getRun, getRunEvents, type Run, type RunEvent } from "@/lib/api";
import { useRunEvents } from "@/lib/useRunEvents";
import { applyLatestEventToRun } from "@/lib/runs";
import { StatusBadge } from "@/components/StatusBadge";
import { EventTimeline } from "@/components/EventTimeline";

export default function RunDetailPage({ params }: PageProps<"/runs/[id]">) {
  const { id: runId } = use(params);
  const { token } = useRequireAuth();
  const [run, setRun] = useState<Run | null>(null);
  const [initialEvents, setInitialEvents] = useState<RunEvent[]>([]);
  const [loaded, setLoaded] = useState(false);
  const { events: liveEvents } = useRunEvents(token, runId);

  useEffect(() => {
    if (!token) return;
    Promise.all([getRun(token, runId), getRunEvents(token, runId)]).then(([fetchedRun, fetchedEvents]) => {
      setRun(fetchedRun);
      setInitialEvents(fetchedEvents);
      setLoaded(true);
    });
  }, [token, runId]);

  // The WS connection backfills this run's full history itself on connect (see backend), so the
  // REST-fetched initial events and the WS's own events overlap -- dedupe by id, keep order.
  const events = useMemo(() => {
    const byId = new Map<number, RunEvent>();
    for (const event of [...initialEvents, ...liveEvents]) byId.set(event.id, event);
    return [...byId.values()].sort((a, b) => a.id - b.id);
  }, [initialEvents, liveEvents]);

  // Derived, not stored -- a pure function of (run, events), computed at render time instead of
  // a separate effect writing into its own state.
  const mergedRun = useMemo(() => (run ? applyLatestEventToRun(run, events) : null), [run, events]);

  if (!token || !loaded || !mergedRun) return null;

  return (
    <main className="mx-auto w-full max-w-3xl space-y-6 px-6 py-8">
      <div className="flex items-start justify-between gap-4">
        <h1 className="text-lg font-semibold">{mergedRun.prompt}</h1>
        <StatusBadge status={mergedRun.status} />
      </div>
      <EventTimeline events={events} />
    </main>
  );
}
