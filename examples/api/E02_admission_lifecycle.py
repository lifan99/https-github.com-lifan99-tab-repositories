"""单事件循环的准入与生命周期练习；用离线资源演示去重、满载拒绝及关闭顺序。"""

import asyncio


class Rejected(Exception):
    """携带公开 HTTP 状态码和稳定错误码的教学准入异常。"""
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


class Admission:
    """仅在单个事件循环内使用的容量与活动标识管理器。"""
    def __init__(self, capacity=2):
        self.capacity = capacity
        self.active_ids = set()
        self.closing = False

    def enter(self, request_id):
        # 检查和登记之间没有 await；这个保证只适用于同一事件循环。
        """先判断关闭，再判断重复标识，最后检查容量；拒绝时不占用名额。"""
        if self.closing:
            raise Rejected(503, "service_unavailable")
        if request_id in self.active_ids:
            raise Rejected(409, "duplicate_request")
        if len(self.active_ids) >= self.capacity:
            raise Rejected(429, "capacity_exceeded")
        self.active_ids.add(request_id)

    def leave(self, request_id):
        """只释放本次成功准入的活动标识。"""
        self.active_ids.remove(request_id)


class FakeResource:
    """模拟多个审核共享的客户端，用 closed 标记检查资源关闭顺序。"""
    def __init__(self):
        self.closed = False
        self.calls = []

    async def call(self, request_id, started, release):
        """通过开始和放行事件控制执行，确认等待期间共享资源未提前关闭。"""
        assert not self.closed
        self.calls.append(request_id)
        started.set()
        await release.wait()
        assert not self.closed
        return request_id

    async def aclose(self):
        self.closed = True


async def run_one(admission, resource, request_id, started, release):
    """成功准入后执行资源调用，无论成功、异常还是取消都释放自己的标识。"""
    admission.enter(request_id)
    try:
        return await resource.call(request_id, started, release)
    finally:
        admission.leave(request_id)


async def main():
    """演示满载拒绝、重复请求、取消后复用、标识重用及任务先于资源关闭。"""
    admission = Admission(2)
    resource = FakeResource()
    tasks = []
    start1, start2 = asyncio.Event(), asyncio.Event()
    release1, release2 = asyncio.Event(), asyncio.Event()

    async def expect_rejection(request_id, expected_status):
        before = list(resource.calls)
        try:
            await run_one(admission, resource, request_id, asyncio.Event(), asyncio.Event())
        except Rejected as exc:
            assert exc.status == expected_status
            assert resource.calls == before
            print(f"{request_id}：{exc.status} {exc.code}；新增模型调用 0 次")
        else:
            raise AssertionError("Expected rejection")

    try:
        async with asyncio.timeout(5):
            task1 = asyncio.create_task(run_one(admission, resource, "R1", start1, release1))
            task2 = asyncio.create_task(run_one(admission, resource, "R2", start2, release2))
            tasks.extend((task1, task2))
            await start1.wait()
            await start2.wait()
            assert len(admission.active_ids) == 2

            await expect_rejection("R1", 409)  # 重复标识优先于满载判断。
            await expect_rejection("R3", 429)
            task1.cancel()
            try:
                await task1
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("Expected cancellation")
            assert admission.active_ids == {"R2"}
            assert not resource.closed

            ready = asyncio.Event()
            ready.set()
            assert await run_one(admission, resource, "R3", asyncio.Event(), ready) == "R3"
            release2.set()
            assert await task2 == "R2"
            assert not admission.active_ids

            # 只在执行期间去重；完成后重用标识会重新执行，没有持久化幂等。
            assert await run_one(admission, resource, "R1", asyncio.Event(), ready) == "R1"
            assert resource.calls.count("R1") == 2
            print("取消后名额恢复，R2 独立完成；结束后复用 R1 会重新执行。")

            admission.closing = True
            await expect_rejection("R4", 503)
    finally:
        admission.closing = True
        for task in tasks:
            if not task.done():
                task.cancel()
        # 先等待所有任务退出并释放名额，再关闭它们共同借用的资源。
        await asyncio.gather(*tasks, return_exceptions=True)
        await resource.aclose()

    assert all(task.done() for task in tasks)
    assert not admission.active_ids and resource.closed
    print("退出顺序检查通过：任务结束、名额释放，然后关闭共享资源。")


if __name__ == "__main__":
    asyncio.run(main())
