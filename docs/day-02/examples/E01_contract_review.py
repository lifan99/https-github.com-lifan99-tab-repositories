"""D2 offline success / bad quote demo: run with PYTHONPATH=. from mvp."""

import argparse
from dataclasses import asdict
import json

from review_system.workflow import WorkflowError, run_review


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--invalid-quote", action="store_true")
    args = parser.parse_args()
    original = "仅用内存保存记录，重启后历史仍在。"
    report = {
        "summary": "历史保留承诺缺少恢复机制支持。", "verdict": "needs_revision",
        "findings": [{
            "category": "logic", "severity": "high",
            "message": "仅用进程内存不能支持重启后的历史恢复。",
            "suggestion": "修改承诺，或另行设计和验证恢复机制。",
            "start": 8 if args.invalid_quote else 9, "end": 16, "quote": "重启后历史仍在",
        }],
        "limitations": ["人工编写的离线示例，未调用模型或核验外部事实。"],
    }

    class FakeClient:
        def __init__(self):
            self.calls = 0
            self.outputs = iter(["A: 定位历史保留承诺。", "C: 质疑恢复依据。", json.dumps(report)])

        async def complete(self, *, model, messages):
            self.calls += 1
            return next(self.outputs)

    client = FakeClient()
    print("FAKE: all responses are synthetic; no network calls.")
    try:
        result = run_review(
            original, client, analyst_model="fake-a", critic_model="fake-c", judge_model="fake-j",
        )
    except WorkflowError as exc:
        if not args.invalid_quote:
            raise
        assert exc.record.stages[-1].error_code == "invalid_output"
        assert exc.record.final_review is None
        assert len(exc.completed) == 2
        print(str(exc))
        print("Preserved:", len(exc.completed))
        record = exc.record
    else:
        assert not args.invalid_quote
        assert result.record.final_review.verdict == "needs_revision"
        print(json.dumps(asdict(result.record.final_review), ensure_ascii=False, indent=2))
        record = result.record
    assert client.calls == 3
    print("Stages:", [stage.status for stage in record.stages])
    print("Model calls:", client.calls)


if __name__ == "__main__":
    main()
