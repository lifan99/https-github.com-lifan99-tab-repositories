"""生成 LangChain 分步学习手册的 HTML 与 EPUB；仅使用标准库。"""

from pathlib import Path

from book_export import build

if __name__ == "__main__":
    build(
        source=Path(__file__).resolve().parent / "LangChain项目学习手册.md",
        book_title="从现有项目学 LangChain",
        metadata="6 个核心任务 · 普通 Python 前置确认 · 3 份查阅附录 · 每次学习一小节",
        description="从字典、函数和上下文传递，逐步理解调用、消息、模板与链式组合，再对照三角色项目。",
        expected_sections=17,
        expected_appendices=3,
        min_chinese=8_000,
    )
