"""Tracks the in-process asyncio.Task currently executing each run (registered via
asyncio.current_task() from inside agent_runner._run_agent_loop), plus an optional "kill hook"
an engine can attach once it has spawned a real OS subprocess -- so POST /runs/{id}/cancel has
something to actually interrupt. In-memory only, same single-worker assumption already
documented for event_bus's EventBus: a server restart loses this registry, which is why
cancel_run's router handler still falls back to marking the run cancelled directly when a task
isn't found here.

Two real bugs were found and fixed live while building this, both worth knowing about before
touching this code again:
1. cancel_run's router handler must be `async def`, not a plain `def`. FastAPI runs sync
   endpoints in a threadpool worker thread; task.cancel() and an engine's kill hook (e.g.
   CliAgentEngine's process.kill) both need to run on the SAME thread as the event loop that
   actually owns that Task/Process. Calling them cross-thread isn't safe with asyncio and was
   confirmed live to make Stop take anywhere from ~10s to nearly 2 minutes to actually land,
   instead of the near-instant delivery it produces once called from the right thread.
2. The kill hook exists because task.cancel() alone doesn't reliably interrupt a CliAgentEngine
   run promptly -- the task is typically suspended awaiting the next line of the subprocess's
   stdout, and killing the process directly is what wakes that pending read right away, instead
   of leaving it to whatever asyncio/cancellation timing would otherwise apply. But the engine's
   own CancelledError handler must NOT also call `await process.wait()` as a fallback once this
   hook has already killed the process -- confirmed live that calling wait() a second time after
   an out-of-band kill hangs forever on this Windows environment, even though the process is, in
   fact, already dead (see CliAgentEngine.run's own comment for the full explanation).
"""

import asyncio
from collections.abc import Callable

_tasks: dict[str, asyncio.Task] = {}
_kill_hooks: dict[str, Callable[[], None]] = {}


def register(run_id: str, task: asyncio.Task) -> None:
    _tasks[run_id] = task

    def _cleanup(_: asyncio.Task) -> None:
        _tasks.pop(run_id, None)
        _kill_hooks.pop(run_id, None)

    task.add_done_callback(_cleanup)


def set_kill_hook(run_id: str, hook: Callable[[], None]) -> None:
    _kill_hooks[run_id] = hook


def cancel(run_id: str) -> bool:
    task = _tasks.get(run_id)
    if task is None or task.done():
        return False

    hook = _kill_hooks.get(run_id)
    if hook is not None:
        try:
            hook()
        except Exception:
            # Best-effort: the process may have already exited on its own in the race between
            # this check and the kill attempt. Either way, task.cancel() below still runs.
            pass

    task.cancel()
    return True
