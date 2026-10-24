"""显式选择的离线演示客户端；返回固定答案，不作为真实模型失败后的备用实现。"""

import asyncio
import json


class DemoClient:
    """根据上下文判断当前角色，返回可通过契约校验的固定演示结果。"""
    async def complete(self, *, model, messages):
        """让出一次事件循环以模拟异步接口；不联网，也不评价材料质量。"""
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
