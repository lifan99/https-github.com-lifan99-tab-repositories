"""两阶段调用练习参考答案：用 Mock 验证输入校验和前序结果传递。"""

from unittest.mock import Mock

def review_pair(text, client):
    """输入合法后先分析再质疑；第二次调用只使用第一次调用的结果。"""
    if not isinstance(text, str):
        raise TypeError("text must be str")
    if not text.strip():
        raise ValueError("text must not be blank")
    analysis = client.complete(stage="analysis", text=text)
    critique = client.complete(stage="critique", text=analysis)
    return analysis, critique

client = Mock()
# 依次返回预置答案，并检查每次调用的关键字参数，验证两阶段之间的数据传递。
client.complete.side_effect = ["A", "C"]
assert review_pair("U", client) == ("A", "C")
assert [call.kwargs for call in client.complete.call_args_list] == [
    {"stage": "analysis", "text": "U"},
    {"stage": "critique", "text": "A"},
]
empty_client = Mock()
try:
    review_pair(" \n", empty_client)
except ValueError:
    empty_client.complete.assert_not_called()
else:
    raise AssertionError("Expected ValueError")
print("两阶段教学练习验证通过")
