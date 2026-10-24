"""JSON 请求示例：观察上下文、消息正文与 HTTP 字节之间的两层序列化。"""

import json
from io import BytesIO

context = {"original_input": "请审查", "analyst_output": "初审"}
# 上下文先成为消息 content 的 JSON 字符串，外层消息列表再编码为 HTTP JSON 正文。
messages = [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
body = json.dumps({"model": "fake", "messages": messages, "stream": False}).encode("utf-8")

decoded_body = json.loads(body)
# 外层解析只得到消息对象；content 仍是字符串，需要再解析一次才能还原上下文。
decoded_context = json.loads(decoded_body["messages"][0]["content"])
assert decoded_context == context

response = BytesIO(b'{"choices":[{"message":{"content":"OK"}}]}')
payload = json.load(response)
print(decoded_context)
print(payload["choices"][0]["message"]["content"])
