"""任务 4：比较逐步执行与 prompt | model | parser；全程离线。"""

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


def main():
    prompt = ChatPromptTemplate.from_messages([
        ("system", "你是 Analyst，请分析给定材料。"),
        ("human", "{original_input}"),
    ])
    model = FakeListChatModel(responses=["[fake] 固定初审回答。"])
    parser = StrOutputParser()
    context = {"original_input": "历史只在本次运行期间保留。"}

    value = prompt.invoke(context)
    message = model.invoke(value)
    direct = parser.invoke(message)

    chain = prompt | model | parser
    composed = chain.invoke(context)
    assert direct == composed == "[fake] 固定初审回答。"
    print("逐步执行：", direct)
    print("链式执行：", composed)
    print("返回类型：", type(composed).__name__)


if __name__ == "__main__":
    main()
