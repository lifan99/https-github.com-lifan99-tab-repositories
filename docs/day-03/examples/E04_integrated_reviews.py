"""D3 application-core demo: concurrent reviews, total timeout, cancellation, reuse."""

import asyncio
import json

from review_system.workflow import ReviewRun, WorkflowError, run_review_async


MODELS = dict(analyst_model="a", critic_model="c", judge_model="j")


class FakeClient:
    def __init__(self):
        self.entered = asyncio.Event()
        self.cleaned = asyncio.Event()

    async def complete(self, *, model, messages):
        original = json.loads(messages[1]["content"])["original_input"]
        await asyncio.sleep(0)
        if original == "slow" and model == "c":
            self.entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                self.cleaned.set()
        if model == "j":
            return json.dumps({"summary": original, "verdict": "pass", "findings": [],
                               "limitations": ["Synthetic offline demonstration."]})
        return f"{model}:{original}"


async def main():
    print("FAKE: no provider requests; this exercises the actual async workflow.")
    slots = asyncio.Semaphore(2)
    client = FakeClient()
    results = await asyncio.gather(*[
        run_review_async(name, client, **MODELS, slots=slots) for name in ["R1", "R2"]
    ])
    assert [result.record.final_review.summary for result in results] == ["R1", "R2"]
    print("Concurrent reviews: separate R1/R2 reports; 3 stages each.")

    try:
        await run_review_async("slow", client, **MODELS, slots=slots, total_timeout_seconds=0.02)
    except WorkflowError as exc:
        assert exc.record.error_code == "total_timeout"
        assert len(exc.completed) == 1 and client.cleaned.is_set()
        print("Total deadline: Analyst preserved; Critic cleaned; Judge skipped.")
    else:
        raise AssertionError("Expected total timeout")

    client = FakeClient()
    run = ReviewRun()
    task = asyncio.create_task(run_review_async("slow", client, **MODELS, slots=slots, run=run))
    try:
        await client.entered.wait()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            assert run.record.status == "cancelled"
            assert len(run.responses) == 1 and client.cleaned.is_set()
            print("Cancellation: propagated and awaited; Analyst remains available.")
        else:
            raise AssertionError("Cancellation must propagate")
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    result = await run_review_async("after-cancel", client, **MODELS, slots=slots)
    assert result.record.status == "succeeded"
    print("Capacity reused: a new review completed after failure and cancellation.")


async def bounded():
    async with asyncio.timeout(5):
        await main()


if __name__ == "__main__":
    asyncio.run(bounded())
