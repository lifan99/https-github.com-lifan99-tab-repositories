"""离线超时教学示例：区分单次模型预算、整次审核预算和其他来源的 TimeoutError。"""

import asyncio


class ModelTimeout(Exception):
    """标记单次模型调用的时间预算耗尽。"""
    pass


class ReviewTimeout(Exception):
    """标记整份审核的时间预算耗尽。"""
    pass


async def limited_call(operation, seconds):
    """仅在本层定时器确实到期时转换异常，保留其他来源的 TimeoutError。"""
    scope = asyncio.timeout(seconds)
    try:
        async with scope:
            return await operation()
    except TimeoutError as exc:
        if not scope.expired():
            raise
        raise ModelTimeout("model_timeout") from exc


async def review(model_seconds, total_seconds, completed, cleaned):
    """两个阶段共用一个总截止时间，每次模型调用另有独立预算。"""
    loop = asyncio.get_running_loop()
    deadline = loop.time() + total_seconds
    scope = asyncio.timeout_at(deadline)

    async def analyst():
        await asyncio.sleep(0)
        return "A"

    async def critic():
        """无限等待模拟卡住的模型；定时取消进入 finally，标记清理完成。"""
        try:
            await asyncio.Event().wait()  # 故意不放行，等待外层定时器取消。
        finally:
            cleaned.set()

    try:
        async with scope:
            for operation in (analyst, critic):
                if loop.time() >= deadline:
                    raise ReviewTimeout("total_timeout")
                completed.append(await limited_call(operation, model_seconds))
    except TimeoutError as exc:
        if not scope.expired():
            raise
        raise ReviewTimeout("total_timeout") from exc
    if loop.time() >= deadline:
        raise ReviewTimeout("total_timeout")


async def main():
    """分别触发模型超时和总超时，检查部分回答与清理，再验证无关超时不被误分类。"""
    cases = [
        (0.02, 5.0, ModelTimeout, "单次模型预算耗尽"),
        (5.0, 0.02, ReviewTimeout, "整次审核预算耗尽"),
    ]
    for model_seconds, total_seconds, expected, label in cases:
        completed = []
        cleaned = asyncio.Event()
        try:
            await review(model_seconds, total_seconds, completed, cleaned)
        except expected as exc:
            assert completed == ["A"]
            assert cleaned.is_set()
            print(f"{label}：{exc}；保留 A；Critic 已清理")
        else:
            raise AssertionError("Expected timeout")

    # 业务操作自行抛出 TimeoutError，不等于本层预算到期。
    async def unrelated_timeout():
        raise TimeoutError("unrelated")

    try:
        await limited_call(unrelated_timeout, 5)
    except TimeoutError as exc:
        assert str(exc) == "unrelated"
        print("其他来源的 TimeoutError：未误归类为模型预算耗尽")
    else:
        raise AssertionError("Expected original TimeoutError")


if __name__ == "__main__":
    asyncio.run(main())
