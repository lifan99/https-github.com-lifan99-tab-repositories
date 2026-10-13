from http.client import BadStatusLine, IncompleteRead
from io import BytesIO
import json
from unittest.mock import Mock, patch

import pytest

from review_system.clients import LLMError, OpenAICompatibleClient
from review_system.config import Settings
from review_system.workflow import MAX_INPUT_CHARS, WorkflowError, run_review


MODELS = dict(analyst_model="analysis-model", critic_model="critique-model", judge_model="judge-model")


def test_order_context_prompts_and_final_response():
    client = Mock()
    client.complete.side_effect = ["Analysis", "Critique", "Verdict"]
    callback = Mock()

    result = run_review("Original proposal", client, **MODELS, on_response=callback)

    assert [r.agent for r in result.responses] == ["Analyst", "Critic", "Judge"]
    assert [r.content for r in result.responses] == ["Analysis", "Critique", "Verdict"]
    assert result.final_response == "Verdict"
    calls = [call.kwargs for call in client.complete.call_args_list]
    assert [call["model"] for call in calls] == list(MODELS.values())
    assert len({call["messages"][0]["content"] for call in calls}) == 3
    assert all([m["role"] for m in call["messages"]] == ["system", "user"] for call in calls)
    assert [json.loads(call["messages"][1]["content"]) for call in calls] == [
        {"original_input": "Original proposal"},
        {"original_input": "Original proposal", "analyst_output": "Analysis"},
        {"original_input": "Original proposal", "analyst_output": "Analysis", "critic_output": "Critique"},
    ]
    assert [call.args[0] for call in callback.call_args_list] == list(result.responses)


@pytest.mark.parametrize("user_input", ["", " \n\t"])
def test_blank_input_makes_no_calls(user_input):
    client = Mock()
    with pytest.raises(ValueError, match="Enter text"):
        run_review(user_input, client, **MODELS)
    client.complete.assert_not_called()


@pytest.mark.parametrize("length", [MAX_INPUT_CHARS - 1, MAX_INPUT_CHARS])
def test_input_at_or_below_character_limit_is_preserved(length):
    client = Mock()
    client.complete.side_effect = ["Analysis", "Critique", "Verdict"]
    user_input = "测" * length
    result = run_review(user_input, client, **MODELS)
    assert result.final_response == "Verdict"
    for call in client.complete.call_args_list:
        assert json.loads(call.kwargs["messages"][1]["content"])["original_input"] == user_input


def test_oversized_input_makes_no_calls():
    client = Mock()
    with pytest.raises(ValueError, match=f"at most {MAX_INPUT_CHARS:,} characters"):
        run_review("x" * (MAX_INPUT_CHARS + 1), client, **MODELS)
    client.complete.assert_not_called()


@pytest.mark.parametrize("failed_index", [0, 1, 2])
@pytest.mark.parametrize("error_type", [RuntimeError, ValueError])
def test_callback_failure_stops_calls_and_preserves_current_response(failed_index, error_type):
    client = Mock()
    client.complete.side_effect = ["Analysis", "Critique", "Verdict"]
    error = error_type("synthetic-private-detail")
    callback = Mock(side_effect=[None] * failed_index + [error])
    with pytest.raises(WorkflowError, match="Response callback failed") as caught:
        run_review("Input", client, **MODELS, on_response=callback)
    assert caught.value.agent == ["Analyst", "Critic", "Judge"][failed_index]
    assert [item.content for item in caught.value.completed] == ["Analysis", "Critique", "Verdict"][:failed_index + 1]
    assert callback.call_args.args[0] == caught.value.completed[-1]
    assert client.complete.call_count == failed_index + 1
    assert callback.call_count == failed_index + 1
    assert caught.value.__cause__ is error
    assert "synthetic-private-detail" not in str(caught.value)


def test_callback_cancellation_propagates():
    client = Mock()
    client.complete.return_value = "Analysis"
    callback = Mock(side_effect=KeyboardInterrupt())
    with pytest.raises(KeyboardInterrupt):
        run_review("Input", client, **MODELS, on_response=callback)
    assert client.complete.call_count == 1


@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_failure_stops_workflow_and_preserves_completed_outputs(failed_index):
    client = Mock()
    client.complete.side_effect = ["Completed"] * failed_index + [LLMError("Provider request timed out.")]
    with pytest.raises(WorkflowError) as caught:
        run_review("Input", client, **MODELS)
    assert caught.value.agent == ["Analyst", "Critic", "Judge"][failed_index]
    assert len(caught.value.completed) == failed_index
    assert client.complete.call_count == failed_index + 1
    assert "timed out" in str(caught.value)


@pytest.mark.parametrize("response", ["", "   ", None])
def test_invalid_model_output_stops_workflow(response):
    client = Mock()
    client.complete.return_value = response
    with pytest.raises(WorkflowError, match="empty or non-text"):
        run_review("Input", client, **MODELS)
    assert client.complete.call_count == 1


@pytest.mark.parametrize("failed_index", [0, 1, 2])
@pytest.mark.parametrize("error_type", [IncompleteRead, BadStatusLine])
def test_http_protocol_failure_preserves_completed_outputs(failed_index, error_type):
    settings = Settings("qwen", "https://example.invalid/v1", "test-placeholder", "m", "m", "m", "m")
    responses = [
        BytesIO(json.dumps({"choices": [{"message": {"content": f"Completed {index}"}}]}).encode())
        for index in range(failed_index)
    ]
    error = error_type(b"partial" if error_type is IncompleteRead else "invalid status")
    callback = Mock()
    with patch("review_system.clients.urlopen", side_effect=responses + [error]) as send:
        with pytest.raises(WorkflowError, match="interrupted") as caught:
            run_review("Input", OpenAICompatibleClient(settings), **MODELS, on_response=callback)
    assert caught.value.agent == ["Analyst", "Critic", "Judge"][failed_index]
    assert [item.content for item in caught.value.completed] == [
        f"Completed {index}" for index in range(failed_index)
    ]
    assert [item.model for item in caught.value.completed] == list(MODELS.values())[:failed_index]
    assert [call.args[0] for call in callback.call_args_list] == list(caught.value.completed)
    assert send.call_count == failed_index + 1
