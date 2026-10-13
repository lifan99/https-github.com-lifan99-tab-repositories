from typing import Protocol

class Client(Protocol):
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str: ...

class FixedClient:
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        return "fixed response"

class EchoClient:
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        return messages[0]["content"]

def review(text: str, client: Client) -> str:
    return client.complete(
        model="teaching-model",
        messages=[{"role": "user", "content": text}],
    )

print(review("hello", FixedClient()))
print(review("hello", EchoClient()))
