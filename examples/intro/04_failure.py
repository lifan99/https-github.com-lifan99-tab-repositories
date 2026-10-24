"""独立教学示例：异常中断后续语句；不模拟完整业务状态。"""


def critic():
    """主动抛出异常，模拟第二个阶段失败。"""
    raise RuntimeError("模拟 Critic 失败")


def judge():
    """若前一阶段抛出异常，此函数不会被调用。"""
    print("Judge 启动了")
    return "固定最终回答"


completed = ["Analyst 的固定回答"]
try:
    # 函数先执行，成功后才 append；异常会跳过当前 append 及后续 Judge 调用。
    completed.append(critic())
    completed.append(judge())
except RuntimeError as error:
    print("失败原因：", error)

print("保留的回答：", completed)
