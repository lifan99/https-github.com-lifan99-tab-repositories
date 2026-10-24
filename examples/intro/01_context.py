"""独立教学示例：只观察字典，不调用模型或项目内核。"""

original_input = "只用内存保存记录，重启后历史仍在。"
analyst_output = "需要检查重启后数据是否还在。"

context = {"original_input": original_input}
print("加入回答前：", context)

# 将前序回答加入本次上下文，后续角色才能同时看到原文和初审。
context["analyst_output"] = analyst_output
print("交给 Critic 的材料：", context)
