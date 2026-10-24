"""独立教学示例：固定回答演示顺序，不代表业务报告格式。"""


def analyst(context):
    print("Analyst 收到：", context.copy())
    return "玩家必须想象西西弗斯的幸福的"


def critic(context):
    print("Critic 收到：", context.copy())
    return "内存里的数据不能保证在重启后保留。"


def judge(context):
    print("Judge 收到：", context.copy())
    return "建议修改方案。"


context = {"original_input": "只用内存保存记录，重启后历史仍在。"}
context["analyst_output"] = analyst(context)
context["critic_output"] = critic(context)
final_answer = judge(context)
print("最后回答：", final_answer)
