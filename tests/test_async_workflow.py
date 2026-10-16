import asyncio
import json
import time
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from review_system.clients import AsyncOpenAICompatibleClient, LLMError
from review_system.config import Settings
from review_system.workflow import ReviewRun, WorkflowError, run_review, run_review_async

MODELS = dict(analyst_model="a", critic_model="c", judge_model="j")


def output(model, original):
    if model != "j":
        return f"{model}:{original}"
    return json.dumps({"summary": original, "verdict": "pass", "findings": [], "limitations": []})


def execute(scenario):
    async def bounded():
        async with asyncio.timeout(5):
            await scenario()
    asyncio.run(bounded())


async def cleanup(tasks):
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


def test_two_reviews_overlap_third_queues_and_contexts_stay_isolated():
    async def scenario():
        slots = asyncio.Semaphore(2)
        release = asyncio.Event()
        names = ("R1", "R2", "R3")
        entered = {name: asyncio.Event() for name in names}
        calls = {name: [] for name in names}
        runs = {name: ReviewRun() for name in names}
        active = peak = 0

        async def complete(*, model, messages):
            nonlocal active, peak
            context = json.loads(messages[1]["content"])
            original = context["original_input"]
            calls[original].append((model, context))
            if model == "a":
                active += 1
                peak = max(peak, active)
                entered[original].set()
                try:
                    await release.wait()
                finally:
                    active -= 1
            return output(model, original)

        client = Mock(complete=AsyncMock(side_effect=complete))
        tasks = []
        try:
            for name in names[:2]:
                tasks.append(asyncio.create_task(run_review_async(name, client, **MODELS, slots=slots, run=runs[name])))
            await asyncio.gather(entered["R1"].wait(), entered["R2"].wait())
            tasks.append(asyncio.create_task(run_review_async("R3", client, **MODELS, slots=slots, run=runs["R3"])))
            await asyncio.sleep(0)  # Give the newly scheduled task a chance to reach its queue.
            assert runs["R3"].record.status == "queued"
            assert not entered["R3"].is_set()
            assert peak == 2
            release.set()
            results = await asyncio.gather(*tasks)
            for name, result in zip(names, results, strict=True):
                assert calls[name] == [
                    ("a", {"original_input": name, "review_mode": "logic"}),
                    ("c", {"original_input": name, "review_mode": "logic", "analyst_output": f"a:{name}"}),
                    ("j", {"original_input": name, "review_mode": "logic", "analyst_output": f"a:{name}", "critic_output": f"c:{name}"}),
                ]
                assert result.record.final_review.summary == name
                assert result.record.status == "succeeded"
            assert client.complete.await_count == 9
        finally:
            await cleanup(tasks)

    execute(scenario)


@pytest.mark.parametrize("model_seconds,total_seconds,code", [
    (0.02, 2, "model_timeout"), (2, 0.02, "total_timeout"), (0.02, 0.02, "total_timeout"),
])
def test_model_and_total_deadlines_preserve_partial_results(model_seconds, total_seconds, code):
    async def scenario():
        cleaned = asyncio.Event()
        run = ReviewRun()
        slots = asyncio.Semaphore(1)

        async def complete(*, model, messages):
            if model == "a":
                return "A"
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()

        client = Mock(complete=AsyncMock(side_effect=complete))
        with pytest.raises(WorkflowError) as caught:
            await run_review_async("Input", client, **MODELS, run=run, slots=slots,
                                   model_timeout_seconds=model_seconds, total_timeout_seconds=total_seconds)
        assert caught.value.record is run.record
        assert run.record.error_code == code
        assert run.record.status == "failed"
        assert [stage.status for stage in run.record.stages] == ["succeeded", "failed", "skipped"]
        assert run.record.stages[1].error_code == code
        assert [item.content for item in run.responses] == ["A"]
        assert run.record.final_review is None
        assert cleaned.is_set()
        assert client.complete.await_count == 2
        async with slots:
            pass

    execute(scenario)


def test_total_budget_is_not_restarted_after_analyst():
    async def scenario():
        calls = []

        async def complete(*, model, messages):
            calls.append(model)
            if model == "a":
                await asyncio.sleep(0.03)
                return "A"
            if model == "c":
                await asyncio.sleep(0.03)
            return output(model, "Input")

        with pytest.raises(WorkflowError) as caught:
            await run_review_async("Input", Mock(complete=AsyncMock(side_effect=complete)), **MODELS,
                                   model_timeout_seconds=2, total_timeout_seconds=0.05)
        assert caught.value.record.error_code == "total_timeout"
        assert calls == ["a", "c"]
        assert len(caught.value.completed) == 1

    execute(scenario)


@pytest.mark.parametrize("cancel", [False, True])
def test_queue_timeout_or_cancel_never_calls_model_or_releases_unowned_slot(cancel):
    async def scenario():
        slots = asyncio.Semaphore(1)
        await slots.acquire()
        run = ReviewRun()
        client = Mock(complete=AsyncMock())
        task = asyncio.create_task(run_review_async(
            "Queued", client, **MODELS, run=run, slots=slots,
            total_timeout_seconds=2 if cancel else 0.02,
        ))
        try:
            await asyncio.sleep(0)
            assert run.record.status == "queued"
            if cancel:
                task.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task
            else:
                with pytest.raises(WorkflowError) as caught:
                    await task
                assert caught.value.agent == "Review"
            assert run.record.error_code == ("cancelled" if cancel else "total_timeout")
            assert [stage.status for stage in run.record.stages] == ["skipped"] * 3
            assert run.responses == ()
            assert run.record.final_review is None
            client.complete.assert_not_awaited()
            assert slots.locked()
            slots.release()
            await slots.acquire()
            assert slots.locked()  # There is still exactly one slot.
            slots.release()
        finally:
            await cleanup([task])

    execute(scenario)


def test_cancel_one_review_then_peer_and_new_review_use_shared_http_client():
    async def scenario():
        settings = Settings("qwen", "https://example.invalid/v1", "synthetic-key", "m", "a", "c", "j")
        entered, cleaned = asyncio.Event(), asyncio.Event()
        calls = []

        async def handle(request):
            body = json.loads(request.content)
            original = json.loads(body["messages"][1]["content"])["original_input"]
            model = body["model"]
            calls.append((original, model))
            if (original, model) == ("R1", "c"):
                entered.set()
                try:
                    await asyncio.Event().wait()
                finally:
                    cleaned.set()
            return httpx.Response(200, json={"choices": [{"message": {"content": output(model, original)}}]})

        tasks = []
        run1, run2 = ReviewRun(), ReviewRun()
        slots = asyncio.Semaphore(1)
        async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as http:
            client = AsyncOpenAICompatibleClient(settings, http)
            try:
                task1 = asyncio.create_task(run_review_async("R1", client, **MODELS, slots=slots, run=run1))
                tasks.append(task1)
                await entered.wait()
                task2 = asyncio.create_task(run_review_async("R2", client, **MODELS, slots=slots, run=run2))
                tasks.append(task2)
                await asyncio.sleep(0)
                assert run2.record.status == "queued"
                task1.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await task1
                assert cleaned.is_set() and task1.cancelled()
                assert run1.record.status == "cancelled"
                assert [stage.status for stage in run1.record.stages] == ["succeeded", "cancelled", "skipped"]
                assert [item.content for item in run1.responses] == ["a:R1"]
                assert run1.record.final_review is None
                assert ("R1", "j") not in calls
                assert (await task2).record.final_review.summary == "R2"
                assert not http.is_closed
                assert (await run_review_async("R3", client, **MODELS, slots=slots)).record.final_review.summary == "R3"
            finally:
                await cleanup(tasks)
        assert http.is_closed
        assert all(task.done() for task in tasks)

    execute(scenario)


def test_failure_does_not_cancel_independent_peer():
    async def scenario():
        gate = asyncio.Event()
        both_entered = asyncio.Event()
        count = 0

        async def complete(*, model, messages):
            nonlocal count
            original = json.loads(messages[1]["content"])["original_input"]
            if model == "a":
                count += 1
                if count == 2:
                    both_entered.set()
                await gate.wait()
            if original == "bad" and model == "c":
                raise LLMError("Synthetic failure")
            return output(model, original)

        client = Mock(complete=AsyncMock(side_effect=complete))
        slots = asyncio.Semaphore(2)
        tasks = [asyncio.create_task(run_review_async(name, client, **MODELS, slots=slots)) for name in ["bad", "good"]]
        try:
            await both_entered.wait()
            gate.set()
            failed, succeeded = await asyncio.gather(*tasks, return_exceptions=True)
            assert isinstance(failed, WorkflowError)
            assert failed.record.error_code == "model_error"
            assert succeeded.record.final_review.summary == "good"
        finally:
            await cleanup(tasks)

    execute(scenario)


@pytest.mark.parametrize("error, expected", [
    (LLMError("network timeout", code="network_timeout"), "network_timeout"),
    (TimeoutError("unrelated private timeout"), "model_error"),
])
def test_error_is_not_mislabeled_as_timer_expiry(error, expected):
    async def scenario():
        with pytest.raises(WorkflowError) as caught:
            await run_review_async("Input", Mock(complete=AsyncMock(side_effect=error)), **MODELS)
        assert caught.value.record.error_code == expected
        assert "unrelated private" not in str(caught.value)
    execute(scenario)


@pytest.mark.parametrize("field", ["model_timeout_seconds", "total_timeout_seconds"])
@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf"), True, "5"])
def test_invalid_budgets_do_not_start_models(field, value):
    async def scenario():
        client = Mock(complete=AsyncMock())
        run = ReviewRun()
        with pytest.raises(ValueError, match=field):
            await run_review_async("Input", client, **MODELS, run=run, **{field: value})
        assert run.record is None
        client.complete.assert_not_called()
    execute(scenario)


def test_callback_overruns_total_budget_cannot_publish_final_report():
    async def scenario():
        async def complete(*, model, messages):
            return output(model, "Input")

        def callback(response):
            if response.agent == "Judge":
                time.sleep(0.03)  # Deliberately block to verify the explicit publication check.

        with pytest.raises(WorkflowError) as caught:
            await run_review_async("Input", Mock(complete=AsyncMock(side_effect=complete)), **MODELS,
                                   on_response=callback, total_timeout_seconds=0.01)
        assert caught.value.record.error_code == "total_timeout"
        assert len(caught.value.completed) == 3
        assert caught.value.record.final_review is None
    execute(scenario)


def test_swallowing_model_timer_cancellation_cannot_return_success():
    async def scenario():
        async def complete(**kwargs):
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                return "too late"

        with pytest.raises(WorkflowError) as caught:
            await run_review_async("Input", Mock(complete=AsyncMock(side_effect=complete)), **MODELS,
                                   model_timeout_seconds=0.02, total_timeout_seconds=2)
        assert caught.value.record.error_code == "model_timeout"
        assert caught.value.completed == ()
    execute(scenario)


def test_progress_snapshots_and_one_shot_run_handle():
    async def scenario():
        run = ReviewRun()
        snapshots = []

        async def complete(*, model, messages):
            snapshots.append(run.record)
            return output(model, "Input")

        client = Mock(complete=AsyncMock(side_effect=complete))
        result = await run_review_async("Input", client, **MODELS, run=run)
        assert [[stage.status for stage in record.stages] for record in snapshots] == [
            ["running", "pending", "pending"], ["succeeded", "running", "pending"],
            ["succeeded", "succeeded", "running"],
        ]
        assert result.record is run.record
        assert run.record.status == "succeeded"
        with pytest.raises(ValueError, match="only be used once"):
            await run_review_async("Other", client, **MODELS, run=run)
        assert client.complete.await_count == 3
    execute(scenario)


def test_sync_facade_rejects_nested_event_loop():
    async def scenario():
        client = Mock(complete=AsyncMock())
        with pytest.raises(RuntimeError, match="await run_review_async"):
            run_review("Input", client, **MODELS)
        client.complete.assert_not_called()
    execute(scenario)


def test_blocking_client_cannot_overrun_model_budget_and_publish_success():
    async def scenario():
        async def complete(**kwargs):
            time.sleep(0.03)
            return "too late"

        with pytest.raises(WorkflowError) as caught:
            await run_review_async("Input", Mock(complete=AsyncMock(side_effect=complete)), **MODELS,
                                   model_timeout_seconds=0.01, total_timeout_seconds=2)
        assert caught.value.record.error_code == "model_timeout"
        assert caught.value.completed == ()
    execute(scenario)
