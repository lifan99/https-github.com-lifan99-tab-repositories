import json
from review_system.workflow import run_review

class FakeClient:
    def __init__(self):
        self.calls = []
        self.outputs = iter(["A", "C", "J"])

    def complete(self, *, model, messages):
        self.calls.append((model, json.loads(messages[1]["content"])))
        return next(self.outputs)

client = FakeClient()
result = run_review(
    "U", client,
    analyst_model="fake-a", critic_model="fake-c", judge_model="fake-j",
    on_response=lambda response: print(response.agent, response.content),
)
assert result.final_response == "J"
for model, context in client.calls:
    print(model, list(context))
