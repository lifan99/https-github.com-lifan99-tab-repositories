import json
from review_system.workflow import run_review

JUDGE_TEXT = json.dumps({
    "summary": "Synthetic review", "verdict": "pass", "findings": [],
    "limitations": ["Offline teaching example; no factual verification."],
})

class FakeClient:
    def __init__(self):
        self.calls = []
        self.outputs = iter(["A", "C", JUDGE_TEXT])

    async def complete(self, *, model, messages):
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
print(client.calls[1])
