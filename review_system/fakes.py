"""Explicit, deterministic offline demonstrations; never used as a live fallback."""

import asyncio
import json


class DemoClient:
    async def complete(self, *, model, messages):
        await asyncio.sleep(0)
        context = json.loads(messages[1]["content"])
        if "critic_output" in context:
            return json.dumps({
                "summary": "离线演示报告：未调用真实模型，不能据此判断材料质量。",
                "verdict": "insufficient_evidence", "findings": [],
                "limitations": ["固定 fake 输出，仅验证程序链路，未进行实际审核或外部核验。"],
            }, ensure_ascii=False)
        if "analyst_output" in context:
            return "[fake] Critic 演示回答；未评估真实材料。"
        return "[fake] Analyst 演示回答；未评估真实材料。"
