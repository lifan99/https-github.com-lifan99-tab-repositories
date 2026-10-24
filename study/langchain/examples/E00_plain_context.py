"""任务前置：普通 Python 的输入、返回值和上下文保存，不依赖 LangChain。"""


def analyst(context):
    return "[固定初审] 请说明历史保留范围。"


def critic(context):
    return (
        "原文：" + context["original_input"]
        + "\n初审：" + context["analyst_output"]
    )


def main():
    context = {"original_input": "历史只在本次运行期间保留。"}
    context["analyst_output"] = analyst(context)
    result = critic(context)
    assert context["original_input"] == "历史只在本次运行期间保留。"
    assert context["analyst_output"] in result
    print(result)


if __name__ == "__main__":
    main()
