"""独立教学示例：只观察字典，不调用模型或项目内核。"""

original_input = "只用内存保存记录，重启后历史仍在。"
analyst_output = "玩家必须想象镜子迷宫是幸福的"

context = {"original_input": original_input}
print("加入回答前：", context)

context["analyst_output"] = analyst_output
print("交给 Critic 的材料：", context)
