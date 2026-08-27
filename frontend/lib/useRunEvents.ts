"use client";

import { useEffect, useRef, useState } from "react";
import { buildRunsWebSocketUrl, type RunEvent } from "@/lib/api";

interface UseRunEventsResult {
  events: RunEvent[];
  connected: boolean;
}

/**
 * Subscribes to /ws/runs (optionally filtered to one run) and accumulates events as they
 * arrive, deduped by id -- safe to call even though a filtered connection re-backfills its
 * run's full history on every (re)connect, since duplicates from that are simply dropped.
 * Reconnects with exponential backoff on disconnect. This is the one genuinely new frontend
 * pattern in this series versus the sibling projects' SSE-over-fetch approach.
 */
export function useRunEvents(token: string | null, runId?: string): UseRunEventsResult {
  const [events, setEvents] = useState<RunEvent[]>([]);
  const [connected, setConnected] = useState(false);
  const seenIds = useRef<Set<number>>(new Set());

  useEffect(() => {
    if (!token) return;

    // Reset accumulated state for the new (token, runId) subscription -- e.g. navigating
    // between two different /runs/[id] pages, which App Router re-renders in place rather than
    // remounting. Mutating a ref here is fine (only *reading* a ref during render is
    // disallowed); the matching setEvents([]) is deliberately deferred to the socket's first
    // onopen callback below rather than called here, synchronously, in the effect body --
    // React's stricter modern lint rules (react-hooks/set-state-in-effect) flag that pattern as
    // cascading-render-prone, even though the reset is logically "at effect start." Gated on
    // `isFirstOpen` so a later *reconnect* within this same effect's lifetime (network hiccup,
    // not a subscription change) doesn't also wipe already-accumulated events -- especially
    // important for the fleet view, which never backfills, so a mid-session reconnect there
    // would otherwise permanently lose every status update observed before it.
    seenIds.current = new Set();
    let isFirstOpen = true;

    let socket: WebSocket | null = null;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let cancelled = false;
    let attempt = 0;

    function connect() {
      if (cancelled) return;
      socket = new WebSocket(buildRunsWebSocketUrl(token as string, runId));

      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
        if (isFirstOpen) {
          isFirstOpen = false;
          setEvents([]);
        }
      };

      socket.onmessage = (messageEvent: MessageEvent<string>) => {
        const event = JSON.parse(messageEvent.data) as RunEvent;
        if (seenIds.current.has(event.id)) return;
        seenIds.current.add(event.id);
        setEvents((prev) => [...prev, event]);
      };

      socket.onclose = () => {
        setConnected(false);
        if (cancelled) return;
        const delay = Math.min(1000 * 2 ** attempt, 15000);
        attempt += 1;
        reconnectTimer = setTimeout(connect, delay);
      };

      socket.onerror = () => {
        socket?.close();
      };
    }

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      socket?.close();
    };
  }, [token, runId]);

  return { events, connected };
}
