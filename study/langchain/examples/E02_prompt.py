"""任务 2：观察 Critic 提示词接收的变量和生成的消息；不调用模型。"""

from langchain_core.prompts import ChatPromptTemplate


def main():
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是 Critic。核对原文与初审，指出有依据的遗漏。"),
        ("human", "原文：{original_input}\n初审：{analyst_output}"),
    ])
    context = {
        "original_input": "历史只在本次运行期间保留。",
        "analyst_output": "[固定初审] 请说明历史保留范围。",
    }
    value = prompt.invoke(context)
    messages = value.to_messages()
    assert len(messages) == 2
    assert context["original_input"] in messages[1].content
    assert context["analyst_output"] in messages[1].content
    print("模板变量：", sorted(prompt.input_variables))
    for message in messages:
        print(message.type, message.content)


if __name__ == "__main__":
    main()
