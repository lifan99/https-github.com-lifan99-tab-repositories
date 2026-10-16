"""HTTP 补充练习 Q07–Q09；只修改本文件中的三个 TODO。"""

from urllib.request import Request

from review_system.config import Settings


def build_request(
    base_url: str,
    api_key: str,
    *,
    model: str,
    messages: list[dict[str, str]],
) -> Request:
    """Q07：构造带 JSON 字节正文和不可转发认证头的 POST 请求。"""
    # TODO：仅构造请求；不要发送网络请求，不要改写 messages。
    raise NotImplementedError("请完成 Q07：build_request")


def parse_response(response) -> str:
    """Q08：从可读响应提取非空白文本；结构或内容错误转为 LLMError。"""
    # TODO：不关闭传入对象；生命周期由调用方管理。保留原始文本空白。
    raise NotImplementedError("请完成 Q08：parse_response")


def complete_with_transport(
    settings: Settings,
    *,
    model: str,
    messages: list[dict[str, str]],
    send,
) -> str:
    """Q09：用注入的 send 发送请求、管理响应资源、统一传输异常。"""
    # TODO：复用前两个函数。send(request, timeout=...) 由题目提供。
    # 不导入 urlopen；不读取 .env；不重试；不要把异常吞掉返回空字符串。
    raise NotImplementedError("请完成 Q09：complete_with_transport")
