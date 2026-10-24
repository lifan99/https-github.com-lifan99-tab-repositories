"""Offline, worked examples for the U1 asyncio lecture."""

import argparse
import asyncio
import time
from collections.abc import Awaitable, Callable


async def download(name: str, trace: list[str]) -> str:
    """Simulate a cooperative wait; no network request is made."""
    trace.append(f"{name}:start")
    await asyncio.sleep(0)
    trace.append(f"{name}:end")
    return f"data:{name}"


async def marker(trace: list[str]) -> None:
    trace.append("marker")


async def immediate() -> str:
    return "ready"


async def demo_creation() -> list[str]:
    trace: list[str] = []
    job = download("a", trace)
    trace.append("created")
    result = await job
    trace.append(result)
    return trace


async def demo_sequential() -> list[str]:
    trace: list[str] = []
    first = await download("a", trace)
    second = await download("b", trace)
    trace.append(f"results:{first},{second}")
    return trace


async def demo_tasks() -> list[str]:
    trace: list[str] = []
    first_task = asyncio.create_task(download("a", trace))
    second_task = asyncio.create_task(download("b", trace))
    trace.append("scheduled")
    first = await first_task
    second = await second_task
    trace.append(f"results:{first},{second}")
    return trace


async def demo_ready() -> list[str]:
    trace: list[str] = []
    peer = asyncio.create_task(marker(trace))
    trace.append("before-await")
    value = await immediate()
    trace.append(f"after-await:{value}")
    await peer
    return trace


async def demo_blocking() -> list[str]:
    trace: list[str] = []
    peer = asyncio.create_task(marker(trace))
    trace.append("before-block")
    time.sleep(0.02)
    trace.append("after-block")
    await peer
    return trace


async def demo_yielding() -> list[str]:
    trace: list[str] = []
    peer = asyncio.create_task(marker(trace))
    trace.append("before-wait")
    await asyncio.sleep(0)
    trace.append("after-wait")
    await peer
    return trace


async def demo_notification() -> list[str]:
    trace: list[str] = []
    waiting = asyncio.Event()
    released = asyncio.Event()

    async def consumer() -> None:
        trace.append("consumer:waiting")
        waiting.set()
        await released.wait()
        trace.append("consumer:resumed")

    task = asyncio.create_task(consumer())
    await waiting.wait()
    trace.append("controller:working")
    assert not task.done()
    released.set()
    trace.append("controller:signaled")
    assert not task.done()
    await task
    trace.append("controller:joined")
    return trace


DEMOS: dict[str, Callable[[], Awaitable[list[str]]]] = {
    "creation": demo_creation,
    "sequential": demo_sequential,
    "tasks": demo_tasks,
    "ready": demo_ready,
    "blocking": demo_blocking,
    "yielding": demo_yielding,
    "notification": demo_notification,
}


async def main(selection: str) -> None:
    selected = DEMOS if selection == "all" else {selection: DEMOS[selection]}
    for name, demo in selected.items():
        trace = await demo()
        print(f"{name}: {trace}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("demo", nargs="?", choices=["all", *DEMOS], default="all")
    args = parser.parse_args()
    asyncio.run(main(args.demo))
