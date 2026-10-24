"""独立教学示例：接收一份材料，返回一段文字；没有真实模型。"""


def critic(context):
    original = context["original_input"]
    analysis = context["analyst_output"]
    return "原文：" + original + "\n初审：" + analysis


context = {
    "original_input": "玩家必须想象西西弗斯是幸福的",
    "analyst_output": "需要检查重启后数据是否还在。",
}
critic_output = critic(context)
print(critic_output)
