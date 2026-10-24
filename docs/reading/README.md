# 项目连续读物与阅读格式

返回 [项目文档导航](../README.md)。两份读物分别用于连续理解项目和选读关键源码；Markdown、HTML 与 EPUB 为同一内容的不同阅读格式。

| 读物 | 维护源 | 手机格式 |
| --- | --- | --- |
| 项目技术阅读 | [Markdown](项目技术阅读.md) | [HTML](项目技术阅读.html)、[EPUB](项目技术阅读.epub) |
| 代码选读 | [Markdown](../technical/代码选读.md) | [HTML](../technical/代码选读.html)、[EPUB](../technical/代码选读.epub) |

从项目根目录重新生成：

```bash
.venv/bin/python docs/reading/build_book.py
.venv/bin/python docs/reading/build_code_reading.py
```

生成工具仅使用标准库。HTML 与 EPUB 不依赖外部字体或脚本，仓库源码链接显示为文件名；尚未在实体手机阅读器上验收。网络与操作系统基础课位于 `~/ai-engineering/learning/computer-systems/`；项目定制的 [LangChain 教程](../../study/langchain/LangChain项目学习手册.md) 和 [个人进度](../../study/今天.md) 保存在本项目的学习区。
