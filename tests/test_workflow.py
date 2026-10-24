"""同步入口的工作流回归：覆盖角色顺序、上下文传递、回调及失败时的部分结果。"""

import asyncio
import json
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from review_system.clients import AsyncOpenAICompatibleClient, LLMError
from review_system.config import Settings
from review_system.workflow import MAX_INPUT_CHARS, WorkflowError, run_review, run_review_async

MODELS = dict(analyst_model="analysis-model", critic_model="critique-model", judge_model="judge-model")
JUDGE_TEXT = json.dumps({
    "summary": "Synthetic review", "verdict": "pass", "findings": [],
    "limitations": ["Synthetic offline response; no external verification."],
})


def test_order_context_prompts_and_final_response():
    """验证角色顺序、独立提示词、前序上下文及最终回答。"""
    client = Mock(complete=AsyncMock())
    client.complete.side_effect = ["Analysis", "Critique", JUDGE_TEXT]
    callback = Mock()

    result = run_review("Original proposal", client, **MODELS, on_response=callback)

    assert [r.agent for r in result.responses] == ["Analyst", "Critic", "Judge"]
    assert [r.content for r in result.responses] == ["Analysis", "Critique", JUDGE_TEXT]
    assert result.final_response == JUDGE_TEXT
    assert result.record.final_review.verdict == "pass"
    assert [stage.status for stage in result.record.stages] == ["succeeded"] * 3
    assert [stage.raw_output for stage in result.record.stages] == ["Analysis", "Critique", JUDGE_TEXT]
    assert all(stage.error_code is None for stage in result.record.stages)
    calls = [call.kwargs for call in client.complete.call_args_list]
    assert [call["model"] for call in calls] == list(MODELS.values())
    assert len({call["messages"][0]["content"] for call in calls}) == 3
    assert all([m["role"] for m in call["messages"]] == ["system", "user"] for call in calls)
    assert [json.loads(call["messages"][1]["content"]) for call in calls] == [
        {"original_input": "Original proposal", "review_mode": "logic"},
        {"original_input": "Original proposal", "review_mode": "logic", "analyst_output": "Analysis"},
        {"original_input": "Original proposal", "review_mode": "logic", "analyst_output": "Analysis", "critic_output": "Critique"},
    ]
    assert [call.args[0] for call in callback.call_args_list] == list(result.responses)


@pytest.mark.parametrize("user_input", ["", " \n\t"])
def test_blank_input_makes_no_calls(user_input):
    """空白输入直接失败，不调用模型。"""
    client = Mock(complete=AsyncMock())
    with pytest.raises(ValueError, match="Enter text"):
        run_review(user_input, client, **MODELS)
    client.complete.assert_not_called()


@pytest.mark.parametrize("length", [MAX_INPUT_CHARS - 1, MAX_INPUT_CHARS])
def test_input_at_or_below_character_limit_is_preserved(length):
    """上限以内的输入按原样传递，不截断或清理。"""
    client = Mock(complete=AsyncMock())
    client.complete.side_effect = ["Analysis", "Critique", JUDGE_TEXT]
    user_input = "测" * length
    result = run_review(user_input, client, **MODELS)
    assert result.final_response == JUDGE_TEXT
    for call in client.complete.call_args_list:
        assert json.loads(call.kwargs["messages"][1]["content"])["original_input"] == user_input


def test_oversized_input_makes_no_calls():
    """超长输入在第一次模型调用前被拒绝。"""
    client = Mock(complete=AsyncMock())
    with pytest.raises(ValueError, match=f"at most {MAX_INPUT_CHARS:,} characters"):
        run_review("x" * (MAX_INPUT_CHARS + 1), client, **MODELS)
    client.complete.assert_not_called()


@pytest.mark.parametrize("failed_index", [0, 1, 2])
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_callback_failure_stops_calls_and_preserves_current_response(failed_index, error_type):
    """回调失败后停止后续角色，但保留触发该回调的回答。"""
    client = Mock(complete=AsyncMock())
    client.complete.side_effect = ["Analysis", "Critique", JUDGE_TEXT]
    error = error_type("synthetic-private-detail")
    callback = Mock(side_effect=[None] * failed_index + [error])
    with pytest.raises(WorkflowError, match="Response callback failed") as caught:
        run_review("Input", client, **MODELS, on_response=callback)
    assert caught.value.agent == ["Analyst", "Critic", "Judge"][failed_index]
    assert [item.content for item in caught.value.completed] == ["Analysis", "Critique", JUDGE_TEXT][:failed_index + 1]
    assert callback.call_args.args[0] == caught.value.completed[-1]
    assert client.complete.call_count == failed_index + 1
    assert callback.call_count == failed_index + 1
    assert caught.value.__cause__ is error
    assert "synthetic-private-detail" not in str(caught.value)
    assert [stage.status for stage in caught.value.record.stages] == (
        ["succeeded"] * failed_index + ["failed"] + ["skipped"] * (2 - failed_index)
    )
    assert caught.value.record.stages[failed_index].error_code == "callback_error"
    assert caught.value.record.final_review is None


def test_callback_cancellation_propagates():
    """回调触发的任务取消继续向调用方传播。"""
    client = Mock(complete=AsyncMock())
    client.complete.return_value = "Analysis"
    callback = Mock(side_effect=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run_review("Input", client, **MODELS, on_response=callback)
    assert client.complete.call_count == 1


@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_failure_stops_workflow_and_preserves_completed_outputs(failed_index):
    """任一阶段失败后不继续执行，已完成回答保持可读。"""
    client = Mock(complete=AsyncMock())
    client.complete.side_effect = ["Completed"] * failed_index + [LLMError("Provider request timed out.")]
    with pytest.raises(WorkflowError) as caught:
        run_review("Input", client, **MODELS)
    assert caught.value.agent == ["Analyst", "Critic", "Judge"][failed_index]
    assert len(caught.value.completed) == failed_index
    assert client.complete.call_count == failed_index + 1
    assert "timed out" in str(caught.value)
    assert [stage.status for stage in caught.value.record.stages] == (
        ["succeeded"] * failed_index + ["failed"] + ["skipped"] * (2 - failed_index)
    )
    assert caught.value.record.stages[failed_index].error_code == "model_error"
    assert caught.value.record.stages[failed_index].raw_output is None
    assert caught.value.record.final_review is None


@pytest.mark.parametrize("response", ["", "   ", None])
def test_invalid_model_output_stops_workflow(response):
    """非文本或空白回答按模型错误停止流程。"""
    client = Mock(complete=AsyncMock())
    client.complete.return_value = response
    with pytest.raises(WorkflowError, match="empty or non-text"):
        run_review("Input", client, **MODELS)
    assert client.complete.call_count == 1


@pytest.mark.parametrize("failed_index", [0, 1, 2])
@pytest.mark.parametrize("error_type", [httpx.ReadError, httpx.RemoteProtocolError])
def test_http_protocol_failure_preserves_completed_outputs(failed_index, error_type):
    """HTTP 协议中断不丢失此前角色已经完成的回答。"""
    settings = Settings("qwen", "https://example.invalid/v1", "test-placeholder", "m", "m", "m", "m")
    responses = [
        httpx.Response(200, json={"choices": [{"message": {"content": f"Completed {index}"}}]})
        for index in range(failed_index)
    ]
    error = error_type("synthetic interrupted response")
    callback = Mock()
    send = Mock(side_effect=responses + [error])

    async def scenario():
        async with httpx.AsyncClient(transport=httpx.MockTransport(send)) as http_client:
            return await run_review_async(
                "Input", AsyncOpenAICompatibleClient(settings, http_client), **MODELS, on_response=callback,
            )

    with pytest.raises(WorkflowError, match="interrupted") as caught:
        asyncio.run(scenario())
    assert caught.value.agent == ["Analyst", "Critic", "Judge"][failed_index]
    assert [item.content for item in caught.value.completed] == [
        f"Completed {index}" for index in range(failed_index)
    ]
    assert [item.model for item in caught.value.completed] == list(MODELS.values())[:failed_index]
    assert [call.args[0] for call in callback.call_args_list] == list(caught.value.completed)
    assert send.call_count == failed_index + 1


@pytest.mark.parametrize("value", [None, 1, True, [], {}])
def test_non_string_input_makes_no_calls(value):
    """原文不是字符串时不调用模型。"""
    client = Mock(complete=AsyncMock())
    with pytest.raises(ValueError, match="original_input"):
        run_review(value, client, **MODELS)
    client.complete.assert_not_called()


@pytest.mark.parametrize("mode", ["bad", None, [], True])
def test_invalid_mode_makes_no_calls(mode):
    """非法审核模式在调用模型前被拒绝。"""
    client = Mock(complete=AsyncMock())
    with pytest.raises(ValueError, match="review_mode"):
        run_review("Input", client, review_mode=mode, **MODELS)
    client.complete.assert_not_called()


@pytest.mark.parametrize("mode", ["logic", "evidence"])
def test_mode_and_unmodified_original_reach_every_stage(mode):
    """审核模式及未经改写的原文到达所有角色。"""
    client = Mock(complete=AsyncMock())
    client.complete.side_effect = ["Analysis", "Critique", JUDGE_TEXT]
    original = " \n中文🐍\n重复 重复 "
    result = run_review(original, client, review_mode=mode, **MODELS)
    for call in client.complete.call_args_list:
        context = json.loads(call.kwargs["messages"][1]["content"])
        assert context["original_input"] == original
        assert context["review_mode"] == mode
    assert result.record.request.original_input == original
    assert result.record.request.review_mode == mode


@pytest.mark.parametrize("text", [
    "Verdict", '```json\n' + JUDGE_TEXT + '\n```', '{}',
    '{"summary":"a","summary":"b"}', '{"summary":NaN}',
    json.dumps({"summary": "S", "verdict": "banana", "findings": [], "limitations": []}),
    json.dumps({"summary": "S", "verdict": "needs_revision", "findings": [], "limitations": []}),
    json.dumps({"summary": "S", "verdict": "needs_revision", "findings": [{
        "category": "logic", "severity": "high", "message": "M", "suggestion": "S",
        "start": 0, "end": 2, "quote": "wrong",
    }], "limitations": []}),
])
def test_judge_contract_failure_retains_raw_output_but_does_not_publish(text):
    """Judge 契约失败时保存原始输出，但不发布结构化最终报告。"""
    client = Mock(complete=AsyncMock())
    client.complete.side_effect = ["Analysis", "Critique", text]
    callback = Mock()
    with pytest.raises(WorkflowError) as caught:
        run_review("Input", client, **MODELS, on_response=callback)
    error = caught.value
    assert error.agent == "Judge"
    assert [item.content for item in error.completed] == ["Analysis", "Critique"]
    assert [stage.status for stage in error.record.stages] == ["succeeded", "succeeded", "failed"]
    assert error.record.stages[-1].raw_output == text
    assert error.record.stages[-1].error_code == "invalid_output"
    assert error.record.final_review is None
    assert client.complete.call_count == 3
    assert callback.call_count == 2


def test_separate_reviews_do_not_share_state():
    """多次审核的上下文、回答和执行快照互不共享。"""
    first = Mock(complete=AsyncMock())
    first.complete.side_effect = ["A", "C", JUDGE_TEXT]
    result = run_review("First", first, **MODELS)
    second = Mock(complete=AsyncMock())
    second.complete.side_effect = LLMError("failure")
    with pytest.raises(WorkflowError) as caught:
        run_review("Second", second, **MODELS)
    assert result.record.final_review is not None
    assert [stage.status for stage in result.record.stages] == ["succeeded"] * 3
    assert caught.value.record.final_review is None
    assert caught.value.completed == ()
