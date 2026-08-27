"use client";

import { useState, type FormEvent } from "react";
import { Send, Square } from "lucide-react";
import { ApiError, cancelRun, sendMessage, type Run } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Alert, AlertDescription } from "@/components/ui/alert";

interface RunComposerProps {
  token: string;
  run: Run;
  onOptimisticUpdate: (patch: Partial<Run>) => void;
}

const ACTIVE_STATUSES = new Set(["queued", "running"]);

/** The run-detail page's bottom bar: a chat input to continue the conversation once a run has
 * settled, or a Stop button while one is still in flight -- never both at once. Continuing
 * resumes the same underlying claude session (see backend's POST /runs/{id}/messages) rather
 * than starting a fresh, context-free one. */
export function RunComposer({ token, run, onOptimisticUpdate }: RunComposerProps) {
  const [prompt, setPrompt] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isCancelling, setIsCancelling] = useState(false);

  const isActive = ACTIVE_STATUSES.has(run.status);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!prompt.trim() || isSubmitting) return;
    setError(null);
    setIsSubmitting(true);
    try {
      await sendMessage(token, run.id, prompt);
      setPrompt("");
      // Optimistic -- the WS connection will bring the real events/status as they arrive, but
      // there's otherwise a window where the REST-fetched `run` still says "completed" until the
      // first new event lands.
      onOptimisticUpdate({ status: "running" });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Something went wrong. Please try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  async function handleCancel() {
    setError(null);
    setIsCancelling(true);
    try {
      await cancelRun(token, run.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Couldn't stop the run. Please try again.");
    } finally {
      setIsCancelling(false);
    }
  }

  if (isActive) {
    return (
      <div className="space-y-2">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}
        <Button variant="outline" onClick={handleCancel} disabled={isCancelling}>
          <Square className="size-3.5" />
          {isCancelling ? "Stopping..." : "Stop"}
        </Button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-2">
      {error && (
        <Alert variant="destructive">
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}
      <div className="flex items-end gap-2">
        <textarea
          rows={2}
          value={prompt}
          onChange={(event) => setPrompt(event.target.value)}
          placeholder="Continue the conversation..."
          onKeyDown={(event) => {
            if (event.key === "Enter" && !event.shiftKey) {
              event.preventDefault();
              event.currentTarget.form?.requestSubmit();
            }
          }}
          className="w-full resize-none rounded-xl border border-input bg-card px-4 py-3 text-sm shadow-sm outline-none focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50"
        />
        <Button type="submit" disabled={isSubmitting || !prompt.trim()} aria-label="Send">
          <Send />
        </Button>
      </div>
    </form>
  );
}
