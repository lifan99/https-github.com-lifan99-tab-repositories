"""任务 3：观察 AIMessage 和其中的固定回答；不访问供应商。"""

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.prompts import ChatPromptTemplate


def main():
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是 Analyst，请分析给定材料。"),
        ("human", "{original_input}"),
    ])
    model = FakeListChatModel(responses=["[fake] 固定初审回答。"])
    value = prompt.invoke({"original_input": "历史只在本次运行期间保留。"})
    answer = model.invoke(value)
    assert answer.content == "[fake] 固定初审回答。"
    print("返回类型：", type(answer).__name__)
    print("回答正文：", answer.content)


if __name__ == "__main__":
    main()
