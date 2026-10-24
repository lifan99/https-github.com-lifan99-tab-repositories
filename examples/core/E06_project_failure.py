"""真实工作流的离线失败示例：Critic 出错后保留 Analyst，且不调用 Judge。"""

from unittest.mock import AsyncMock, Mock
from review_system.clients import LLMError
from review_system.workflow import WorkflowError, run_review

client = Mock(complete=AsyncMock())
# 第一次调用成功，第二次抛错；通过调用次数可确认第三阶段未启动。
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
