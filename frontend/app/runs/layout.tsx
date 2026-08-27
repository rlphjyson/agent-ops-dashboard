"use client";

import { useEffect, useMemo, useState } from "react";
import { usePathname } from "next/navigation";
import { useRequireAuth } from "@/lib/auth";
import { listRuns, type Run } from "@/lib/api";
import { useRunEvents } from "@/lib/useRunEvents";
import { applyLatestEventToRun } from "@/lib/runs";
import { RunSidebar } from "@/components/RunSidebar";
import { TopBar } from "@/components/TopBar";

export default function RunsLayout({ children }: { children: React.ReactNode }) {
  const { token } = useRequireAuth();
  const pathname = usePathname();
  const [runs, setRuns] = useState<Run[]>([]);
  const [loaded, setLoaded] = useState(false);
  const { events } = useRunEvents(token);

  // Refetches on every route change within /runs, not just on mount: navigating to a
  // newly-created run's own page (RunForm's router.push after POST /runs) is what picks up that
  // new run in the sidebar, since the unfiltered WS stream itself deliberately doesn't backfill
  // (see backend) and so can't be the sole source of "a new run now exists."
  useEffect(() => {
    if (!token) return;
    listRuns(token).then((fetched) => {
      setRuns(fetched);
      setLoaded(true);
    });
  }, [token, pathname]);

  const mergedRuns = useMemo(
    () => runs.map((run) => applyLatestEventToRun(run, events)),
    [runs, events],
  );

  if (!token) return null;

  return (
    <div className="flex h-screen overflow-hidden">
      <RunSidebar runs={mergedRuns} loaded={loaded} />
      <div className="flex flex-1 flex-col overflow-hidden">
        <TopBar />
        <div className="flex-1 overflow-y-auto">{children}</div>
      </div>
    </div>
  );
}
