"""真实工作流的离线追踪：预置三角色回答，观察上下文增加和阶段状态变化。"""

import json
from review_system.workflow import run_review

# 工作流会校验 Judge 输出；离线答案也必须符合真实报告契约。
JUDGE_TEXT = json.dumps({
    "summary": "Synthetic review", "verdict": "pass", "findings": [],
    "limitations": ["Offline teaching example; no factual verification."],
})

class FakeClient:
    """记录每次模型和上下文，按顺序返回预置的 Analyst、Critic、Judge 输出。"""
    def __init__(self):
        self.calls = []
        self.outputs = iter(["A", "C", JUDGE_TEXT])

    async def complete(self, *, model, messages):
        """保存解析后的本次上下文，供调用结束后核对前序回答传递。"""
        self.calls.append((model, json.loads(messages[1]["content"])))
        return next(self.outputs)

client = FakeClient()
result = run_review(
    "U", client,
    analyst_model="fake-a", critic_model="fake-c", judge_model="fake-j",
    on_response=lambda response: print(response.agent, response.content),
)
assert result.final_response == JUDGE_TEXT
assert result.record.final_review.verdict == "pass"
assert [stage.status for stage in result.record.stages] == ["succeeded"] * 3
for model, context in client.calls:
    print(model, list(context))
