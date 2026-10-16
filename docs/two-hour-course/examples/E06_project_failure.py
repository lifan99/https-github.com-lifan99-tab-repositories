from unittest.mock import AsyncMock, Mock
from review_system.clients import LLMError
from review_system.workflow import WorkflowError, run_review

client = Mock(complete=AsyncMock())
client.complete.side_effect = ["A", LLMError("synthetic failure")]

try:
    run_review(
        "U", client,
        analyst_model="fake-a", critic_model="fake-c", judge_model="fake-j",
    )
except WorkflowError as error:
    assert error.agent == "Critic"
    assert [item.content for item in error.completed] == ["A"]
    assert client.complete.call_count == 2
    print(error.agent, len(error.completed))
else:
    raise AssertionError("Expected WorkflowError")
