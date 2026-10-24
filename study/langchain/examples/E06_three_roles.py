"""任务 6：三份独立提示词与固定回答，仅演示顺序和显式上下文传递。

不含项目的预算、阶段快照、回调和报告业务校验，不能替换生产工作流。
"""

import json

from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate


def make_chain(system_text, template_text, fixed_answer):
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_text),
        ("human", template_text),
    ])
    model = FakeListChatModel(responses=[fixed_answer])
    return prompt | model | StrOutputParser()


def main():
    context = {"original_input": "历史只在本次运行期间保留。"}
    analyst = make_chain("你是 Analyst。", "{original_input}", "[fake] 初审 A")
    critic = make_chain(
        "你是 Critic。",
        "原文：{original_input}\n初审：{analyst_output}",
        "[fake] 质疑 C",
    )
    report = json.dumps({
        "summary": "离线演示，未评价材料。",
        "verdict": "insufficient_evidence",
        "findings": [],
        "limitations": ["固定回答，只观察数据传递。"],
    }, ensure_ascii=False)
    judge = make_chain(
        "你是 Judge。",
        "原文：{original_input}\n初审：{analyst_output}\n质疑：{critic_output}",
        report,
    )
    print("Analyst 输入键：", sorted(context))
    context["analyst_output"] = analyst.invoke(context)
    print("Critic 输入键：", sorted(context))
    context["critic_output"] = critic.invoke(context)
    print("Judge 输入键：", sorted(context))
    final_text = judge.invoke(context)
    print("Judge 原始文本：", final_text)
    assert json.loads(final_text)["verdict"] == "insufficient_evidence"


if __name__ == "__main__":
    main()
