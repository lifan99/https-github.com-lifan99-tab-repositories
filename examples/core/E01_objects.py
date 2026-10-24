"""对象与浅复制示例：新列表仍共享内部字典，冻结数据类保护记录字段。"""

from dataclasses import dataclass

@dataclass(frozen=True)
class Response:
    """冻结数据类不能直接重新赋值字段，适合表达已经接收的回答快照。"""
    agent: str
    content: str

records = [{"id": "a", "message": "original"}]
alias = records
# 浅复制只复制外层列表；内部字典仍是同一对象，修改它也会影响原列表。
copied = records.copy()
copied[0]["message"] = "edited"

print("同一外层列表：", alias is records)
print("新的外层列表：", copied is not records)
print("共享内部字典：", copied[0] is records[0])
print("原列表内容：", records)

response = Response("Analyst", "A")
print(response.agent, response.content)
