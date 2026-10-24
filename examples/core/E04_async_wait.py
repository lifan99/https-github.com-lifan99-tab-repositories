"""异步等待示例：比较顺序 await 与 gather 并发等待，返回结果仍保持输入顺序。"""

import asyncio
from time import perf_counter

async def wait_for(label: str) -> str:
    """用可挂起的短等待模拟网络 I/O，不阻塞事件循环。"""
    await asyncio.sleep(0.02)
    return label

async def main():
    """分别计时顺序与并发等待；耗时仅供观察，不用精确时长断言并发行为。"""
    start = perf_counter()
    serial = [await wait_for("X"), await wait_for("Y")]
    serial_seconds = perf_counter() - start

    start = perf_counter()
    concurrent = await asyncio.gather(wait_for("X"), wait_for("Y"))
    concurrent_seconds = perf_counter() - start

    assert serial == concurrent == ["X", "Y"]
    print("顺序等待：", round(serial_seconds, 3))
    print("并发等待：", round(concurrent_seconds, 3))

asyncio.run(main())
