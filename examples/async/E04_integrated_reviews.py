"""D3 真实异步内核演示：使用离线替身验证并发、总超时、取消与名额复用。"""

import asyncio
import json

from review_system.workflow import ReviewRun, WorkflowError, run_review_async


MODELS = dict(analyst_model="a", critic_model="c", judge_model="j")


class FakeClient:
    """普通材料返回固定答案，slow 材料在 Critic 挂起并暴露开始及清理事件。"""
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
    """使用真实审核内核依次演示并发、总超时、取消以及失败后继续接收审核。"""
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
    # 外部取消会直接抛出 CancelledError；保留运行句柄以便取消后读取最后快照。
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
    """给整组演示设置等待上限，避免示例故障时无限挂起。"""
    async with asyncio.timeout(5):
        await main()


if __name__ == "__main__":
    asyncio.run(bounded())
