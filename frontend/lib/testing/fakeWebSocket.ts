import { vi } from "vitest";

/** A minimal fake of the browser WebSocket API, driven manually in tests -- lets useRunEvents be
 * tested without a real socket or a real backend. Each constructed instance is pushed onto
 * `instances` so a test can grab the most recent one and fire its handlers directly. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = [];

  url: string;
  onopen: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  closed = false;

  constructor(url: string) {
    this.url = url;
    FakeWebSocket.instances.push(this);
  }

  close() {
    this.closed = true;
    this.onclose?.();
  }

  // Test helpers -- not part of the real WebSocket API.
  simulateOpen() {
    this.onopen?.();
  }

  simulateMessage(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) });
  }

  simulateClose() {
    this.onclose?.();
  }
}

export function installFakeWebSocket() {
  FakeWebSocket.instances = [];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  vi.stubGlobal("WebSocket", FakeWebSocket as any);
}
