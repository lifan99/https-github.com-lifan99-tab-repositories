"""离线并发教学示例：审核之间并发执行，每份审核内部顺序执行且上下文隔离。"""

import asyncio


ROLES = ("Analyst", "Critic", "Judge")


class FakeClient:
    """用事件屏障保证两份初审实际重叠，同时记录调用顺序、活动数及上下文副本。"""
    def __init__(self):
        self.both_started = asyncio.Event()
        self.started = set()
        self.active = 0
        self.peak = 0
        self.calls = []

    async def complete(self, review_id, role, context):
        # 复制当时的上下文；若只记录字典引用，后续写入会改变先前记录。
        self.calls.append((review_id, role, dict(context)))
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            if role == "Analyst":
                self.started.add(review_id)
                if len(self.started) == 2:
                    self.both_started.set()
                # 第一份审核等待第二份也进入，避免用不稳定的耗时比较判断并发。
                await self.both_started.wait()
            await asyncio.sleep(0)
            return f"{review_id}:{role}"
        finally:
            self.active -= 1


async def review(review_id, client, slots):
    """一份审核独占一个名额，内部角色顺序执行；上下文字典只属于本次调用。"""
    context = {"original_input": review_id}
    completed = []
    async with slots:
        for role in ROLES:
            output = await client.complete(review_id, role, context)
            completed.append(output)
            context[f"{role.lower()}_output"] = output
    return completed


async def main():
    """并发运行两份审核，检查重叠峰值、角色顺序、上下文隔离及任务清理。"""
    client = FakeClient()
    slots = asyncio.Semaphore(2)
    tasks = [asyncio.create_task(review(name, client, slots)) for name in ("R1", "R2")]
    try:
        # 设置宽松的总等待上限，及时发现示例改动导致的死锁。
        async with asyncio.timeout(5):
            results = await asyncio.gather(*tasks)
    finally:
        for task in tasks:
            if not task.done():
                task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    assert client.peak == 2 and client.active == 0
    for review_id, result in zip(("R1", "R2"), results):
        assert result == [f"{review_id}:{role}" for role in ROLES]
        calls = [call for call in client.calls if call[0] == review_id]
        assert [call[1] for call in calls] == list(ROLES)
        expected = {"original_input": review_id}
        for _, role, context in calls:
            assert context == expected
            expected[f"{role.lower()}_output"] = f"{review_id}:{role}"
        print(f"{review_id}: Analyst -> Critic -> Judge；上下文隔离通过")
    print("同时等待的 fake 调用峰值：2；结束后活动调用数：0")


if __name__ == "__main__":
    asyncio.run(main())
