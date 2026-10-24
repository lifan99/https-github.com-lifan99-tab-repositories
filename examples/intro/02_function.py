"""独立教学示例：接收一份材料，返回一段文字；没有真实模型。"""


def critic(context):
    """从上下文读取原文与初审并组合返回；演示函数参数传递，不调用模型。"""
    original = context["original_input"]
    analysis = context["analyst_output"]
    return "原文：" + original + "\n初审：" + analysis


context = {
    "original_input": "只用内存保存记录，重启后历史仍在。",
    "analyst_output": "需要检查重启后数据是否还在。",
}
critic_output = critic(context)
print(critic_output)
