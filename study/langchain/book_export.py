"""从同目录 Markdown 生成可离线阅读的 HTML 和 EPUB 3，仅使用 Python 标准库。

运行：python3 build_langchain.py
只支持本文用到的 Markdown 子集，不是通用 Markdown 转换器。
"""

from __future__ import annotations

import html
import re
import uuid
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZIP_STORED, ZipFile

DIRECTORY = Path(__file__).resolve().parent
TITLE = "多 Agent 审核系统：项目技术阅读"
SOURCE = DIRECTORY / "LangChain项目学习手册.md"
XHTML = "http://www.w3.org/1999/xhtml"
CSS = """html { color-scheme: light dark; }
body { margin: 0 auto; padding: 1.4em 1.1em 4em; max-width: 35em;
  font-family: -apple-system, BlinkMacSystemFont, "PingFang SC", "Microsoft YaHei", sans-serif;
  font-size: 1.125em; line-height: 1.95; color: #26313b; background: #f7f8fa;
  overflow-wrap: anywhere; word-break: normal; }
h1, h2, h3 { line-height: 1.5; font-weight: 600; text-align: left; }
h1 { font-size: 1.65em; margin: 1.8em 0 1em; }
h2 { font-size: 1.35em; margin-top: 2em; }
h3 { font-size: 1.12em; }
p { margin: 0 0 1.15em; orphans: 2; widows: 2; }
a { color: #1d4ed8; text-underline-offset: .2em; }
code { font-family: ui-monospace, "SFMono-Regular", Consolas, monospace;
  font-size: .86em; overflow-wrap: anywhere; }
pre { white-space: pre-wrap; overflow-wrap: anywhere; word-break: break-word;
  padding: .85em; border: 1px solid #cbd5e1; border-radius: .4em; line-height: 1.7; }
blockquote { margin: 1.5em 0; padding-left: 1em; border-left: 3px solid #94a3b8; }
blockquote p { margin: 0; }
ul, ol { padding-left: 1.45em; }
li { margin-bottom: .7em; }
.meta, .chapter-nav { font-size: .8em; color: #526071; }
.chapter-nav { display: flex; flex-wrap: wrap; gap: 1.4em; margin: 2em 0; }
.chapter { border-top: 1px solid #cbd5e1; margin-top: 3em; padding-top: 1em; }
.cover { min-height: 65vh; display: flex; flex-direction: column; justify-content: center; }
summary { cursor: pointer; padding: .7em 0; font-weight: 600; }
@media (min-width: 600px) { body { padding: 2em 1.8em 5em; font-size: 1.25em; } }
@media (prefers-color-scheme: dark) {
  body { background: #151a23; color: #d7deea; }
  a { color: #94bfff; } .meta, .chapter-nav { color: #a6b2c3; }
  pre, .chapter { border-color: #3b4657; }
}
@media print { body { color: #222; background: white; } .chapter-nav { display: none; } }
"""


def inline(text: str) -> str:
    """转义正文；仓库文件链接在独立电子书里显示为文件名，避免失效跳转。"""
    pattern = r"`([^`]+)`|\[([^\]]+)\]\(([^)]+)\)|\*\*([^*]+)\*\*"
    result, offset = [], 0
    for match in re.finditer(pattern, text):
        result.append(html.escape(text[offset:match.start()]))
        code, label, target, strong = match.groups()
        if code is not None:
            result.append(f"<code>{html.escape(code)}</code>")
        elif label is not None:
            escaped = html.escape(label)
            if target.startswith(("https://", "http://", "#")):
                result.append(f'<a href="{html.escape(target, quote=True)}">{escaped}</a>')
            else:
                name = html.escape(Path(target).name)
                result.append(f"{escaped}（<code>{name}</code>）")
        else:
            result.append(f"<strong>{html.escape(strong)}</strong>")
        offset = match.end()
    result.append(html.escape(text[offset:]))
    return "".join(result)


def blocks(markdown: str) -> str:
    result, paragraph, listing = [], [], None
    lines = iter(markdown.splitlines())

    def flush() -> None:
        if paragraph:
            result.append(f'<p>{inline(" ".join(paragraph))}</p>')
            paragraph.clear()

    def close_list() -> None:
        nonlocal listing
        if listing:
            result.append(f"</{listing}>")
            listing = None

    for line in lines:
        if line.startswith("```"):
            flush()
            close_list()
            code = []
            for item in lines:
                if item.startswith("```"):
                    break
                code.append(item)
            result.append("<pre><code>" + html.escape("\n".join(code)) + "</code></pre>")
        elif not line.strip():
            flush()
            close_list()
        elif line.startswith("### "):
            flush()
            close_list()
            result.append(f"<h2>{inline(line[4:])}</h2>")
        elif line.startswith("> "):
            flush()
            close_list()
            result.append(f"<blockquote><p>{inline(line[2:])}</p></blockquote>")
        elif (match := re.match(r"^(?:- |\d+\. )(.+)$", line)):
            flush()
            kind = "ul" if line.startswith("- ") else "ol"
            if listing != kind:
                close_list()
                result.append(f"<{kind}>")
                listing = kind
            result.append(f"<li>{inline(match.group(1))}</li>")
        else:
            close_list()
            paragraph.append(line.strip())
    flush()
    close_list()
    return "\n".join(result)


def xhtml(title: str, body: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n<!DOCTYPE html>\n'
        f'<html xmlns="{XHTML}" xmlns:epub="http://www.idpf.org/2007/ops" '
        'lang="zh-CN" xml:lang="zh-CN"><head><meta charset="utf-8" />'
        f'<title>{html.escape(title)}</title><link rel="stylesheet" href="style.css" />'
        f"</head><body>{body}</body></html>"
    )


def build(
    *,
    source: Path = SOURCE,
    book_title: str = TITLE,
    metadata: str | None = None,
    description: str = "架构与职责、上下文传递、模型通信、报告契约、异步控制、服务、页面和测试。",
    expected_sections: int = 28,
    expected_appendices: int = 3,
    min_chinese: int = 20_000,
    render_blocks=blocks,
    extra_css: str = "",
) -> None:
    text = source.read_text(encoding="utf-8")
    chinese = len(re.findall(r"[\u3400-\u9fff]", text))
    parts = re.split(r"^## (.+)\n", text, flags=re.M)
    chapters = [(parts[i], render_blocks(parts[i + 1])) for i in range(1, len(parts), 2)]
    css = CSS + extra_css
    assert len(chapters) == expected_sections, "文档章节数量与生成配置不符。"
    assert sum(title.startswith("附录") for title, _ in chapters) == expected_appendices
    assert min_chinese <= chinese <= 32_000, "检查阅读篇幅是否发生了显著变化。"
    if metadata is None:
        metadata = f"24 章 · 3 份技术附录 · 约 {chinese / 10000:.1f} 万中文字符，另含术语与代码 · 约两小时阅读"

    toc = "\n".join(
        f'<li><a href="#chapter-{i:02}">{html.escape(title)}</a></li>'
        for i, (title, _) in enumerate(chapters, 1)
    )
    sections = []
    for i, (title, body) in enumerate(chapters, 1):
        links = ['<a href="#contents">回到目录</a>']
        if i > 1:
            links.append(f'<a href="#chapter-{i - 1:02}">上一章</a>')
        if i < len(chapters):
            links.append(f'<a href="#chapter-{i + 1:02}">下一章</a>')
        html_body = body.replace("<h2>", "<h3>").replace("</h2>", "</h3>")
        sections.append(
            f'<section class="chapter" id="chapter-{i:02}"><h2>{html.escape(title)}</h2>'
            + html_body + '<nav class="chapter-nav" aria-label="章节导航">' + "".join(links) + "</nav></section>"
        )
    document = (
        '<!DOCTYPE html><html lang="zh-CN"><head><meta charset="utf-8" />'
        '<meta name="viewport" content="width=device-width, initial-scale=1" />'
        f'<title>{html.escape(book_title)}</title><style>{css}</style></head><body>'
        f'<header><p class="meta">项目技术文档 · 手机阅读版</p><h1>{html.escape(book_title)}</h1>'
        f'<p class="meta">{metadata}</p>'
        f'<p>{html.escape(description)}</p>'
        '<p class="meta">可按主题分次阅读，无需同时操作电脑。字号可用浏览器缩放调整；深浅色跟随系统设置。</p>'
        '</header><details id="contents"><summary>展开文档目录</summary><ol>'
        + toc + '</ol></details><main>' + "\n".join(sections) + '</main></body></html>'
    )
    source.with_suffix(".html").write_text(document, encoding="utf-8")

    identity = "technical-reading" if source == SOURCE else source.stem
    book_id = f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, f'local:multi-agent-mvp:{identity}')}"
    entries = {"EPUB/style.css": css}
    entries["META-INF/container.xml"] = (
        '<?xml version="1.0"?>'
        '<container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0">'
        '<rootfiles><rootfile full-path="EPUB/package.opf" '
        'media-type="application/oebps-package+xml" /></rootfiles></container>'
    )
    entries["EPUB/cover.xhtml"] = xhtml(
        book_title, f'<section class="cover"><p>项目技术文档</p><h1>{html.escape(book_title)}</h1>'
        f'<p>{metadata}</p><p>{html.escape(description)}</p>'
        '<p>依据本地源码 · 2026-10-19</p></section>',
    )
    nav_items, ncx_items, manifest, spine = [], [], [], []
    for i, (title, body) in enumerate(chapters, 1):
        name = f"chapter-{i:02}.xhtml"
        escaped = html.escape(title)
        entries[f"EPUB/{name}"] = xhtml(title, f"<h1>{escaped}</h1>{body}")
        nav_items.append(f'<li><a href="{name}">{escaped}</a></li>')
        ncx_items.append(
            f'<navPoint id="ch{i}" playOrder="{i}"><navLabel><text>{escaped}</text></navLabel>'
            f'<content src="{name}" /></navPoint>'
        )
        manifest.append(f'<item id="ch{i}" href="{name}" media-type="application/xhtml+xml" />')
        spine.append(f'<itemref idref="ch{i}" />')
    entries["EPUB/nav.xhtml"] = xhtml(
        "目录", '<nav epub:type="toc" id="toc"><h1>目录</h1><ol>' + "".join(nav_items) + "</ol></nav>",
    )
    entries["EPUB/toc.ncx"] = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" xml:lang="zh-CN">'
        f'<head><meta name="dtb:uid" content="{book_id}" />'
        '<meta name="dtb:depth" content="1" /><meta name="dtb:totalPageCount" content="0" />'
        '<meta name="dtb:maxPageNumber" content="0" /></head>'
        f'<docTitle><text>{html.escape(book_title)}</text></docTitle><navMap>' + "".join(ncx_items) + "</navMap></ncx>"
    )
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entries["EPUB/package.opf"] = (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="book-id">'
        '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">'
        f'<dc:identifier id="book-id">{book_id}</dc:identifier><dc:title>{html.escape(book_title)}</dc:title>'
        '<dc:language>zh-CN</dc:language><dc:creator>项目技术文档</dc:creator>'
        f'<meta property="dcterms:modified">{modified}</meta></metadata><manifest>'
        '<item id="cover" href="cover.xhtml" media-type="application/xhtml+xml" />'
        '<item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav" />'
        '<item id="ncx" href="toc.ncx" media-type="application/x-dtbncx+xml" />'
        '<item id="css" href="style.css" media-type="text/css" />'
        + "".join(manifest) + '</manifest><spine toc="ncx"><itemref idref="cover" />'
        '<itemref idref="nav" />' + "".join(spine) + '</spine></package>'
    )
    for name, content in entries.items():
        if name.endswith((".xml", ".opf", ".ncx", ".xhtml")):
            ET.fromstring(content)
    with ZipFile(source.with_suffix(".epub"), "w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=ZIP_STORED)
        for name, content in entries.items():
            archive.writestr(name, content.encode("utf-8"))
    print(f"生成 HTML 与 EPUB：{len(chapters)} 节，{chinese:,} 个中文字符。")


if __name__ == "__main__":
    build()
