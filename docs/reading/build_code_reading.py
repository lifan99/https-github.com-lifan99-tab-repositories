"""将代码选读生成手机 HTML 与 EPUB；宽表格转为纵向卡片，仅使用标准库。

运行：.venv/bin/python docs/reading/build_code_reading.py
"""

import re
from pathlib import Path

from build_book import blocks, build, inline

SOURCE = Path(__file__).resolve().parent.parent / "technical" / "代码选读.md"
EXTRA_CSS = """
.table-cards { margin: 1em 0 1.5em; }
.table-card { margin: 0 0 .8em; padding: .8em 1em;
  border: 1px solid #cbd5e1; border-radius: .4em; }
.table-card dt { font-size: .85em; font-weight: 600; color: #526071; }
.table-card dd { margin: .15em 0 .7em; }
.table-card dd:last-child { margin-bottom: 0; }
pre code { font-size: .88em; }
@media (prefers-color-scheme: dark) {
  .table-card { border-color: #3b4657; }
  .table-card dt { color: #a6b2c3; }
}
"""


def cells(line: str) -> list[str]:
    """当前正文的表格单元格不含竖线，按 Markdown 列分隔符拆分即可。"""
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def phone_blocks(markdown: str) -> str:
    """保持普通正文与代码块原样渲染，将代码块外的表格转成纵向字段卡片。"""
    lines = markdown.splitlines()
    result, pending = [], []
    index = 0
    in_code = False
    while index < len(lines):
        line = lines[index]
        if line.startswith("```"):
            in_code = not in_code
        if (
            not in_code
            and line.startswith("|")
            and index + 1 < len(lines)
            and re.fullmatch(r"\|[\s:|\-]+\|", lines[index + 1])
        ):
            result.append(blocks("\n".join(pending)))
            pending.clear()
            headers = cells(line)
            index += 2
            cards = []
            while index < len(lines) and lines[index].startswith("|"):
                values = cells(lines[index])
                if len(values) != len(headers):
                    raise ValueError("代码选读表格的列数不一致。")
                fields = "".join(
                    f"<dt>{inline(header)}</dt><dd>{inline(value)}</dd>"
                    for header, value in zip(headers, values, strict=True)
                )
                cards.append(f'<dl class="table-card">{fields}</dl>')
                index += 1
            result.append('<div class="table-cards">' + "".join(cards) + "</div>")
            continue
        pending.append(line)
        index += 1
    result.append(blocks("\n".join(pending)))
    return "\n".join(result)


if __name__ == "__main__":
    build(
        source=SOURCE,
        book_title="多 Agent 审核系统：代码选读",
        metadata="9 个源码阅读环节 · 离线示例与自测答案 · 依据 2026-10-19 本地源码",
        description=(
            "从角色与上下文读到模型调用、报告校验、失败处理和测试，每次可读一至两节。"
            "片段供阅读，不能覆盖源码；带省略内容的片段不是独立程序。"
            "运行示例须在电脑上的 mvp 项目根目录执行。"
            "仓库链接显示为文件名，便于离线查阅。"
        ),
        expected_sections=11,
        expected_appendices=0,
        min_chinese=3_000,
        render_blocks=phone_blocks,
        extra_css=EXTRA_CSS,
    )
