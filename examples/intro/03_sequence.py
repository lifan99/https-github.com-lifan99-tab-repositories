"""独立教学示例：固定回答演示顺序，不代表业务报告格式。"""


def analyst(context):
    """读取原文并返回固定初审，便于观察后续角色收到哪些字段。"""
    print("Analyst 收到：", context.copy())
    return "需要检查重启后的数据。"


def critic(context):
    """读取已包含初审的上下文，返回固定质疑。"""
    print("Critic 收到：", context.copy())
    return "内存里的数据不能保证在重启后保留。"


def judge(context):
    """读取原文及前两个角色的输出，返回教学用最终回答。"""
    print("Judge 收到：", context.copy())
    return "建议修改方案。"


context = {"original_input": "只用内存保存记录，重启后历史仍在。"}
# 赋值右侧先调用函数，再把返回值写入字典，因此每阶段只看到已完成的前序输出。
context["analyst_output"] = analyst(context)
context["critic_output"] = critic(context)
final_answer = judge(context)
print("最后回答：", final_answer)
