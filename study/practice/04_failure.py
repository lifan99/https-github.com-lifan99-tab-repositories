"""独立教学示例：异常中断后续语句；不模拟完整业务状态。"""


def critic():
    return "Critic 的固定回答"


def judge():
    print("Judge 启动了")
    return "固定最终回答"


completed = ["Analyst 的固定回答"]
try:
    completed.append(critic())
    completed.append(judge())
except RuntimeError as error:
    print("失败原因：", error)

print("保留的回答：", completed)
