import json
from io import BytesIO

context = {"original_input": "请审查", "analyst_output": "初审"}
messages = [{"role": "user", "content": json.dumps(context, ensure_ascii=False)}]
body = json.dumps({"model": "fake", "messages": messages, "stream": False}).encode("utf-8")

decoded_body = json.loads(body)
decoded_context = json.loads(decoded_body["messages"][0]["content"])
assert decoded_context == context

response = BytesIO(b'{"choices":[{"message":{"content":"OK"}}]}')
payload = json.load(response)
print(decoded_context)
print(payload["choices"][0]["message"]["content"])
