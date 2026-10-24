"""课堂工作流回归：用异步替身验证上下文递进、失败停止及空白输入提前拒绝。"""

import json
from unittest.mock import AsyncMock, Mock
import pytest

from review_system.clients import LLMError
from review_system.workflow import WorkflowError, run_review

MODELS = {"analyst_model": "a", "critic_model": "c", "judge_model": "j"}
JUDGE_TEXT = json.dumps({
    "summary": "Synthetic review", "verdict": "pass", "findings": [],
    "limitations": ["Offline teaching example."],
})

def test_context_progression():
    """逐次核对用户消息中的上下文，确认原文、模式和前序回答按阶段累积。"""
    client = Mock(complete=AsyncMock())
    client.complete.side_effect = ["A", "C", JUDGE_TEXT]
    result = run_review("U", client, **MODELS)
    contexts = [
        json.loads(call.kwargs["messages"][1]["content"])
        for call in client.complete.call_args_list
    ]
    assert contexts == [
        {"original_input": "U", "review_mode": "logic"},
        {"original_input": "U", "review_mode": "logic", "analyst_output": "A"},
        {"original_input": "U", "review_mode": "logic", "analyst_output": "A", "critic_output": "C"},
    ]
    assert result.final_response == JUDGE_TEXT
    assert result.record.final_review.verdict == "pass"

@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_failure_stops_calls(failed_index):
    """分别让三个阶段失败，检查已完成回答数及模型调用停止位置。"""
    client = Mock(complete=AsyncMock())
    client.complete.side_effect = ["done"] * failed_index + [LLMError("synthetic failure")]
    with pytest.raises(WorkflowError) as caught:
        run_review("U", client, **MODELS)
    assert len(caught.value.completed) == failed_index
    assert client.complete.call_count == failed_index + 1

def test_blank_input_makes_no_calls():
    """空白输入在模型调用之前失败，避免无效请求消耗资源。"""
    client = Mock(complete=AsyncMock())
    with pytest.raises(ValueError):
        run_review(" \n", client, **MODELS)
    client.complete.assert_not_called()
