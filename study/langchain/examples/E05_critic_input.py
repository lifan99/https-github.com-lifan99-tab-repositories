"""任务 5：显式保存 Analyst 返回值，再查看 Critic 收到的消息。"""

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


def main():
    analyst_prompt = ChatPromptTemplate.from_messages([
        ("system", "你是 Analyst，请分析材料。"),
        ("human", "{original_input}"),
    ])
    analyst_model = FakeListChatModel(responses=["[fake] 固定初审回答。"])
    analyst_chain = analyst_prompt | analyst_model | StrOutputParser()
    context = {"original_input": "历史只在本次运行期间保留。"}
    context["analyst_output"] = analyst_chain.invoke(context)

    critic_prompt = ChatPromptTemplate.from_messages([
        ("system", "你是 Critic，核对原文和初审。"),
        ("human", "原文：{original_input}\n初审：{analyst_output}"),
    ])
    messages = critic_prompt.invoke(context).to_messages()
    assert context["analyst_output"] in messages[1].content
    print("Critic 请求材料：")
    print(messages[1].content)


if __name__ == "__main__":
    main()
