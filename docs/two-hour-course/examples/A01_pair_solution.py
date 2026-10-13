from unittest.mock import Mock

def review_pair(text, client):
    if not isinstance(text, str):
        raise TypeError("text must be str")
    if not text.strip():
        raise ValueError("text must not be blank")
    analysis = client.complete(stage="analysis", text=text)
    critique = client.complete(stage="critique", text=analysis)
    return analysis, critique

client = Mock()
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
