"""协议与替身示例：业务函数只依赖 complete 接口，可换用固定回答或回显实现。"""

from typing import Protocol

class Client(Protocol):
    """只约定调用签名；实现类无需显式继承，只要具备兼容的 complete 方法。"""
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str: ...

class FixedClient:
    """忽略输入，返回固定文本的离线替身。"""
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        return "fixed response"

class EchoClient:
    """把首条消息内容原样返回，用来观察接口参数传递。"""
    def complete(self, *, model: str, messages: list[dict[str, str]]) -> str:
        return messages[0]["content"]

def review(text: str, client: Client) -> str:
    """依赖客户端协议完成一次调用，不关心实际实现是固定回答还是回显。"""
    return client.complete(
        model="teaching-model",
        messages=[{"role": "user", "content": text}],
    )

print(review("hello", FixedClient()))
print(review("hello", EchoClient()))
