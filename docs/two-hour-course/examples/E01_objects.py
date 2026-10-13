from dataclasses import dataclass

@dataclass(frozen=True)
class Response:
    agent: str
    content: str

records = [{"id": "a", "message": "original"}]
alias = records
copied = records.copy()
copied[0]["message"] = "edited"

print("同一外层列表：", alias is records)
print("新的外层列表：", copied is not records)
print("共享内部字典：", copied[0] is records[0])
print("原列表内容：", records)

response = Response("Analyst", "A")
print(response.agent, response.content)
