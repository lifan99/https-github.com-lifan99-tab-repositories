import asyncio
from time import perf_counter

async def wait_for(label: str) -> str:
    await asyncio.sleep(0.02)
    return label

async def main():
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
