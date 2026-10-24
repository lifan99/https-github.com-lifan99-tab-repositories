"""Public contract checks. Run explicitly after implementing the exercise."""

import json

import pytest

import exercise as lab


def test_call_order_and_returned_responses() -> None:
    client = lab.FakeClient()
    result = lab.run_workflow("Use a shared cache.", "logic", client.complete)

    assert [role for role, _ in client.calls] == ["Analyst", "Critic", "Judge"]
    assert result == [
        ("Analyst", "Check cache invalidation."),
        ("Critic", "Consider stale data."),
        ("Judge", "Revise the proposal."),
    ]


@pytest.mark.parametrize("original_input", ["Use a shared cache.", "缓存方案", ""])
def test_each_role_receives_exactly_its_available_materials(original_input: str) -> None:
    client = lab.FakeClient()
    lab.run_workflow(original_input, "logic", client.complete)

    assert len(client.calls) == 3
    assert [json.loads(text) for _, text in client.calls] == [
        {"original_input": original_input, "review_mode": "logic"},
        {
            "original_input": original_input,
            "review_mode": "logic",
            "analyst_output": "Check cache invalidation.",
        },
        {
            "original_input": original_input,
            "review_mode": "logic",
            "analyst_output": "Check cache invalidation.",
            "critic_output": "Consider stale data.",
        },
    ]


def test_replacement_responses_and_mode_are_used() -> None:
    outputs = {"Analyst": "先检查边界。", "Critic": "Check eviction.", "Judge": "Needs evidence."}
    client = lab.FakeClient(outputs)
    result = lab.run_workflow("Plan B", "code", client.complete)

    assert len(client.calls) == 3
    requests = [json.loads(text) for _, text in client.calls]
    assert all(request["review_mode"] == "code" for request in requests)
    assert all(request["original_input"] == "Plan B" for request in requests)
    assert requests[1]["analyst_output"] == outputs["Analyst"]
    assert requests[2]["analyst_output"] == outputs["Analyst"]
    assert requests[2]["critic_output"] == outputs["Critic"]
    assert result == list(outputs.items())


def test_separate_runs_do_not_share_materials() -> None:
    first = lab.FakeClient({"Analyst": "First run only."})
    lab.run_workflow("Plan A", "logic", first.complete)
    second = lab.FakeClient({"Analyst": "Second run only."})
    lab.run_workflow("Plan B", "code", second.complete)

    assert len(second.calls) == 3
    assert json.loads(second.calls[0][1]) == {"original_input": "Plan B", "review_mode": "code"}
    assert json.loads(second.calls[1][1]) == {
        "original_input": "Plan B",
        "review_mode": "code",
        "analyst_output": "Second run only.",
    }
