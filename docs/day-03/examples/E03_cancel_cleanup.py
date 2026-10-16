"""Offline teaching example: cancel, await cleanup, and reuse capacity."""

import asyncio


async def main():
    slots = asyncio.Semaphore(1)
    entered = asyncio.Event()
    cleaned = asyncio.Event()
    second_waiting = asyncio.Event()
    completed = {"R1": [], "R2": []}
    calls = {"R1": [], "R2": []}

    async def first():
        async with slots:
            calls["R1"].append("Analyst")
            completed["R1"].append("A1")
            calls["R1"].append("Critic")
            entered.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned.set()
            calls["R1"].append("Judge")

    async def second():
        second_waiting.set()
        async with slots:
            for role in ("Analyst", "Critic", "Judge"):
                calls["R2"].append(role)
                await asyncio.sleep(0)
                completed["R2"].append(f"R2:{role}")

    tasks = []
    try:
        async with asyncio.timeout(5):
            task1 = asyncio.create_task(first())
            tasks.append(task1)
            await entered.wait()
            task2 = asyncio.create_task(second())
            tasks.append(task2)
            await second_waiting.wait()
            assert calls["R2"] == []

            task1.cancel()
            try:
                await task1
            except asyncio.CancelledError:
                pass  # The owner requested cancellation and has now observed it.
            else:
                raise AssertionError("Cancellation must propagate")

            assert task1.cancelled() and cleaned.is_set()
            await task2
            assert calls["R1"] == ["Analyst", "Critic"]
            assert completed["R1"] == ["A1"]
            assert calls["R2"] == ["Analyst", "Critic", "Judge"]
            assert len(completed["R2"]) == 3
            # Prove capacity can be acquired again without private counters.
            async with slots:
                pass
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    print("R1：取消传播，Critic 清理完成，保留 A1，Judge 未启动")
    print("R2：取得已释放的名额，独立完成三个阶段")
    print("资源：名额可再次取得，创建的两个任务均已结束")


if __name__ == "__main__":
    asyncio.run(main())
