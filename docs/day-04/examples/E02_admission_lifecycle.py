"""Single-event-loop admission exercise, without HTTP or a real model client."""

import asyncio


class Rejected(Exception):
    def __init__(self, status, code):
        super().__init__(code)
        self.status = status
        self.code = code


class Admission:
    def __init__(self, capacity=2):
        self.capacity = capacity
        self.active_ids = set()
        self.closing = False

    def enter(self, request_id):
        # No await between checking and reserving, on this one event loop only.
        if self.closing:
            raise Rejected(503, "service_unavailable")
        if request_id in self.active_ids:
            raise Rejected(409, "duplicate_request")
        if len(self.active_ids) >= self.capacity:
            raise Rejected(429, "capacity_exceeded")
        self.active_ids.add(request_id)

    def leave(self, request_id):
        self.active_ids.remove(request_id)


class FakeResource:
    def __init__(self):
        self.closed = False
        self.calls = []

    async def call(self, request_id, started, release):
        assert not self.closed
        self.calls.append(request_id)
        started.set()
        await release.wait()
        assert not self.closed
        return request_id

    async def aclose(self):
        self.closed = True


async def run_one(admission, resource, request_id, started, release):
    admission.enter(request_id)
    try:
        return await resource.call(request_id, started, release)
    finally:
        admission.leave(request_id)


async def main():
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

            await expect_rejection("R1", 409)  # Duplicate takes priority over full capacity.
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

            # In-flight conflict protection is not persistent idempotency.
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
        await asyncio.gather(*tasks, return_exceptions=True)
        await resource.aclose()

    assert all(task.done() for task in tasks)
    assert not admission.active_ids and resource.closed
    print("退出顺序检查通过：任务结束、名额释放，然后关闭共享资源。")


if __name__ == "__main__":
    asyncio.run(main())
