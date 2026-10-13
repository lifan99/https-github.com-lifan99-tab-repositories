"""Sequential Analyst -> Critic -> Judge orchestration."""

from dataclasses import dataclass
import json
from typing import Callable

from .agents import ANALYST, CRITIC, JUDGE
from .clients import LLMClient, LLMError


MAX_INPUT_CHARS = 20_000


@dataclass(frozen=True)
class AgentResponse:
    agent: str
    model: str
    content: str


@dataclass(frozen=True)
class ReviewResult:
    responses: tuple[AgentResponse, ...]

    @property
    def final_response(self) -> str:
        return self.responses[-1].content


class WorkflowError(RuntimeError):
    def __init__(self, agent: str, cause: Exception, completed: tuple[AgentResponse, ...]):
        super().__init__(f"{agent} failed: {cause}")
        self.agent = agent
        self.completed = completed


def run_review(
    user_input: str,
    client: LLMClient,
    *,
    analyst_model: str,
    critic_model: str,
    judge_model: str,
    on_response: Callable[[AgentResponse], None] | None = None,
) -> ReviewResult:
    """Review bounded input; callback failures stop work and retain current output."""
    if not user_input.strip():
        raise ValueError("Enter text, code, reasoning, or a proposal to review.")
    if len(user_input) > MAX_INPUT_CHARS:
        raise ValueError(f"Input must contain at most {MAX_INPUT_CHARS:,} characters.")
    completed: list[AgentResponse] = []
    context = {"original_input": user_input}
    for agent, model in ((ANALYST, analyst_model), (CRITIC, critic_model), (JUDGE, judge_model)):
        messages = [
            {"role": "system", "content": agent.system_prompt},
            {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
        ]
        try:
            content = client.complete(model=model, messages=messages)
            if not isinstance(content, str) or not content.strip():
                raise LLMError("The model returned empty or non-text content.")
        except LLMError as exc:
            raise WorkflowError(agent.name, exc, tuple(completed)) from exc
        response = AgentResponse(agent.name, model, content)
        completed.append(response)
        context[f"{agent.name.lower()}_output"] = content
        if on_response is not None:
            try:
                on_response(response)
            except Exception as exc:
                # Keep arbitrary callback details out of the user-facing error.
                cause = RuntimeError("Response callback failed.")
                raise WorkflowError(agent.name, cause, tuple(completed)) from exc
    return ReviewResult(tuple(completed))
