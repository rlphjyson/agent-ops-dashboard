import asyncio

import pytest

from app.services import run_registry


async def test_cancel_returns_false_when_no_task_registered() -> None:
    assert run_registry.cancel("no-such-run") is False


async def test_cancel_cancels_the_registered_task_and_returns_true() -> None:
    started = asyncio.Event()

    async def _hang() -> None:
        started.set()
        await asyncio.Event().wait()

    task = asyncio.create_task(_hang())
    run_registry.register("run-1", task)
    await started.wait()

    assert run_registry.cancel("run-1") is True
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancel_returns_false_for_an_already_finished_task() -> None:
    async def _noop() -> None:
        return None

    task = asyncio.create_task(_noop())
    run_registry.register("run-2", task)
    await task

    assert run_registry.cancel("run-2") is False


async def test_register_cleans_up_after_the_task_finishes() -> None:
    async def _noop() -> None:
        return None

    task = asyncio.create_task(_noop())
    run_registry.register("run-3", task)
    await task
    # The done-callback pop runs on a later loop iteration, not synchronously at completion.
    await asyncio.sleep(0)

    assert run_registry.cancel("run-3") is False


async def test_cancel_calls_the_kill_hook_before_cancelling_the_task() -> None:
    # Regression test for a real, live-caught bug: task.cancel() alone was confirmed not to
    # promptly interrupt a CliAgentEngine run on Windows (see run_registry's module docstring) --
    # the kill hook is what actually makes Stop responsive by closing the subprocess's stdout
    # pipe immediately instead of waiting for task cancellation to be cooperatively delivered.
    started = asyncio.Event()
    killed = False

    async def _hang() -> None:
        started.set()
        await asyncio.Event().wait()

    def _kill() -> None:
        nonlocal killed
        killed = True

    task = asyncio.create_task(_hang())
    run_registry.register("run-4", task)
    run_registry.set_kill_hook("run-4", _kill)
    await started.wait()

    assert run_registry.cancel("run-4") is True
    assert killed is True
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_cancel_still_cancels_the_task_when_the_kill_hook_raises() -> None:
    # The hook is best-effort -- e.g. the process may have already exited on its own in the race
    # between the "is this run still in progress" check and the kill attempt.
    started = asyncio.Event()

    async def _hang() -> None:
        started.set()
        await asyncio.Event().wait()

    def _kill() -> None:
        raise ProcessLookupError("already exited")

    task = asyncio.create_task(_hang())
    run_registry.register("run-5", task)
    run_registry.set_kill_hook("run-5", _kill)
    await started.wait()

    assert run_registry.cancel("run-5") is True
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_kill_hook_is_cleaned_up_after_the_task_finishes() -> None:
    async def _noop() -> None:
        return None

    task = asyncio.create_task(_noop())
    run_registry.register("run-6", task)
    run_registry.set_kill_hook("run-6", lambda: None)
    await task
    await asyncio.sleep(0)

    # Nothing left to clean up or call -- cancel() sees no registered task at all now.
    assert run_registry.cancel("run-6") is False
