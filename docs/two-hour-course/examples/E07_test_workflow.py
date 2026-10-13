import json
from unittest.mock import Mock
import pytest

from review_system.clients import LLMError
from review_system.workflow import WorkflowError, run_review

MODELS = {"analyst_model": "a", "critic_model": "c", "judge_model": "j"}

def test_context_progression():
    client = Mock()
    client.complete.side_effect = ["A", "C", "J"]
    result = run_review("U", client, **MODELS)
    contexts = [
        json.loads(call.kwargs["messages"][1]["content"])
        for call in client.complete.call_args_list
    ]
    assert contexts == [
        {"original_input": "U"},
        {"original_input": "U", "analyst_output": "A"},
        {"original_input": "U", "analyst_output": "A", "critic_output": "C"},
    ]
    assert result.final_response == "J"

@pytest.mark.parametrize("failed_index", [0, 1, 2])
def test_failure_stops_calls(failed_index):
    client = Mock()
    client.complete.side_effect = ["done"] * failed_index + [LLMError("synthetic failure")]
    with pytest.raises(WorkflowError) as caught:
        run_review("U", client, **MODELS)
    assert len(caught.value.completed) == failed_index
    assert client.complete.call_count == failed_index + 1

def test_blank_input_makes_no_calls():
    client = Mock()
    with pytest.raises(ValueError):
        run_review(" \n", client, **MODELS)
    client.complete.assert_not_called()
