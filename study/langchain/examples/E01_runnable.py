"""任务 1：同一个普通函数，比较直接调用与 Runnable.invoke。"""

from langchain_core.runnables import RunnableLambda


def read_original(context):
    return context["original_input"]


def main():
    context = {"original_input": "历史只在本次运行期间保留。"}
    step = RunnableLambda(read_original)
    direct = read_original(context)
    wrapped = step.invoke(context)
    assert direct == wrapped
    print("直接调用：", direct)
    print("invoke：", wrapped)
    print("返回类型：", type(wrapped).__name__)


if __name__ == "__main__":
    main()
