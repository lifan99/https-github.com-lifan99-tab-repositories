from unittest.mock import Mock
import pytest
from review_system.workflow import WorkflowError, run_review

def test_critic_callback_failure():
    client = Mock()
    client.complete.side_effect = ["A", "C", "J"]
    original_error = RuntimeError("private-detail")
    callback = Mock(side_effect=[None, original_error])
    with pytest.raises(WorkflowError) as caught:
        run_review(
            "U", client,
            analyst_model="a", critic_model="c", judge_model="j",
            on_response=callback,
        )
    assert caught.value.agent == "Critic"
    assert [item.content for item in caught.value.completed] == ["A", "C"]
    assert client.complete.call_count == 2
    assert callback.call_count == 2
    assert caught.value.__cause__ is original_error
    assert "private-detail" not in str(caught.value)
