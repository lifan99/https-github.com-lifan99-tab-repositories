"""Offline workflow exercise. Implement only run_workflow."""

import json
from collections.abc import Callable


def run_workflow(
    original_input: str,
    review_mode: str,
    call_model: Callable[[str, str], str],
) -> list[tuple[str, str]]:
    """Return ordered role/response pairs according to README.md."""
    # TODO: Implement the workflow according to the lab contract.
    raise NotImplementedError("Implement run_workflow before running the lab.")


class FakeClient:
    """Record request text and return fixed responses without network access."""

    def __init__(self, outputs: dict[str, str] | None = None) -> None:
        self.outputs = {
            "Analyst": "Check cache invalidation.",
            "Critic": "Consider stale data.",
            "Judge": "Revise the proposal.",
        }
        if outputs is not None:
            self.outputs.update(outputs)
        self.calls: list[tuple[str, str]] = []

    def complete(self, role: str, request_text: str) -> str:
        if not isinstance(request_text, str):
            raise TypeError("request_text must be a JSON string.")
        if not isinstance(json.loads(request_text), dict):
            raise ValueError("request_text must encode a JSON object.")
        self.calls.append((role, request_text))
        return self.outputs[role]


def main() -> None:
    client = FakeClient()
    try:
        responses = run_workflow("Use a shared cache.", "logic", client.complete)
    except NotImplementedError as exc:
        print(exc)
        return

    print("REQUESTS")
    for role, request_text in client.calls:
        print(role, json.loads(request_text))

    print("RESPONSES")
    for role, response in responses:
        print(role, response)


if __name__ == "__main__":
    main()
