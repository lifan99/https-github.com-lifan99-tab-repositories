"""Check lecture claims, without elapsed-time thresholds or network calls."""

import asyncio

import demos


def test_coroutine_body_starts_after_creation_record() -> None:
    assert asyncio.run(demos.demo_creation()) == ["created", "a:start", "a:end", "data:a"]


def test_direct_awaits_preserve_sequential_dependency() -> None:
    assert asyncio.run(demos.demo_sequential()) == [
        "a:start", "a:end", "b:start", "b:end", "results:data:a,data:b",
    ]


def test_scheduled_tasks_overlap_and_finish_before_results() -> None:
    trace = asyncio.run(demos.demo_tasks())
    assert trace[0] == "scheduled"
    assert trace[-1] == "results:data:a,data:b"
    assert sorted(trace[1:-1]) == ["a:end", "a:start", "b:end", "b:start"]
    for name in ("a", "b"):
        assert trace.index(f"{name}:start") < trace.index(f"{name}:end")
    assert max(trace.index("a:start"), trace.index("b:start")) < min(
        trace.index("a:end"), trace.index("b:end"),
    )


def test_immediately_returning_coroutine_does_not_yield_to_peer() -> None:
    assert asyncio.run(demos.demo_ready()) == ["before-await", "after-await:ready", "marker"]


def test_synchronous_sleep_does_not_schedule_peer_on_loop_thread() -> None:
    assert asyncio.run(demos.demo_blocking()) == ["before-block", "after-block", "marker"]


def test_asyncio_sleep_zero_gives_ready_peer_a_turn() -> None:
    assert asyncio.run(demos.demo_yielding()) == ["before-wait", "marker", "after-wait"]


def test_notification_makes_waiter_runnable_without_preempting_notifier() -> None:
    assert asyncio.run(demos.demo_notification()) == [
        "consumer:waiting", "controller:working", "controller:signaled",
        "consumer:resumed", "controller:joined",
    ]
