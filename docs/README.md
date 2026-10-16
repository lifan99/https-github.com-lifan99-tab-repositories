# 文档索引与阅读路线

修订：2026-10-16。当前运行方式以 [根 README](../README.md) 为入口，工程约束以 [AGENTS.md](../AGENTS.md) 为准，已实现能力与待验证项统一维护在 [实施总览](implementation-status.md)。

## 先按目的选择入口

| 你现在要做什么 | 从这里开始 |
| --- | --- |
| 安装、启动 fake/live 后端与 UI | [根 README](../README.md) |
| 确认哪些功能已经实现 | [实施总览](implementation-status.md) |
| 第一次读懂一次审核 | [第一日阅读材料](第一日阅读材料.md)，约 90 分钟 |
| 分日学习现有代码 | 下方 D1 → D4 路线；勾选用于个人学习，不要求重复实施 |
| 两小时精读架构 | [两小时课程](two-hour-course/完整讲义.md) |
| 自己重建局部模块 | [从零教程](从零手撕多智能体审查项目.md)，练习放 mvp 内独立目录 |
| 查 Python、接口、命令或排错 | [代码与指令参考指南](代码与指令参考指南.md) |
| 查看某阶段实际做了什么 | 下方历史实施记录，保留当时日期和测试数量 |

## 分日学习：现有源码 → 独立练习 → 行为验证

| 顺序 | 计划与阅读 | 学习产出 |
| --- | --- | --- |
| HTTP 前置（按需） | [HTTP 前置知识](HTTP前置知识：读懂模型客户端.md) → [12 题练习](HTTP补充练习.md) → [参考答案](HTTP补充练习参考答案.md) | 理解请求与响应；同步 urllib 专用于教学，结尾对照异步主路径 |
| D1 | [第一日阅读材料](第一日阅读材料.md) | 画对 UI→HTTP→Service→内核→模型调用链，写对上下文与部分结果 |
| D2 | [第二日计划](第二日计划任务.md) + [第二日阅读](第二日阅读材料.md) | 契约字段、JSON、引用和阶段记录，合法/非法样例验证 |
| D3 | [第三日计划](第三日计划任务.md) + [第三日阅读](第三日阅读材料.md) | 异步、状态隔离、三层超时、取消、名额与资源复用 |
| D4 | [第四日计划](第四日计划任务.md) + [第四日阅读](第四日阅读材料.md) | 请求/响应、准入、409/429、错误映射与应用生命周期 |
| 贯穿学习 | [固定审核输入](samples/d1-logic-proposal.txt)、[参考指南](代码与指令参考指南.md)、[从零教程](从零手撕多智能体审查项目.md) | 用可复现输入与明确断言核对理解 |

当前日计划与正文已按现有异步/HTTP 实现修订。工程已实现不代表个人已掌握；练习与自测记录在自己的笔记中，不改历史测试结果来表示学习完成。

## 示例与测试：区分验证范围

所有命令在项目根目录执行，先按根 README 安装依赖。模型相关示例全部使用 fake/Mock，不需要真实凭据。

| 示例 | 范围 | 入口 |
| --- | --- | --- |
| 课堂 E01—E04 | 对象、协议、两层 JSON、等待等独立概念 | [课堂目录](two-hour-course/examples/) |
| 课堂 E05/E06 | 实际业务内核的成功与 Critic 失败 | 下方命令 |
| D2 E01 | 实际内核的合法报告与非法引用 | [脚本](day-02/examples/E01_contract_review.py)，可加 --invalid-quote |
| D3 E01—E03 | 标准库并发、期限、取消概念 | [目录](day-03/examples/) |
| D3 E04 | 实际内核的并发、总期限、取消与复用 | [集成脚本](day-03/examples/E04_integrated_reviews.py) |
| D4 E01/E02 | 响应契约与准入的独立概念，无监听 | [目录](day-04/examples/) |
| D4 E03 | 真实回环 HTTP 的 201/422/504，fake 模型 | [HTTP 演示](day-04/examples/E03_local_http_smoke.py) |
| D5 E01 | AppTest→真实回环 HTTP→API→内核，fake 模型 | [UI 演示](day-05/examples/E01_ui_http_smoke.py) |
| 课堂 E08 | Streamlit 会话计数，不运行审核 | [页面示例](two-hour-course/examples/E08_streamlit_counter.py) |

```bash
# 默认业务、课堂和 HTTP 参考实现等统一检查，不需要监听端口。
.venv/bin/python scripts/check.py

# 实际业务内核的 fake 成功与失败。
PYTHONPATH=. .venv/bin/python docs/two-hour-course/examples/E05_project_trace.py
PYTHONPATH=. .venv/bin/python docs/two-hour-course/examples/E06_project_failure.py

# 课堂额外测试不属于默认 tests/ 集合。
.venv/bin/python -m pytest -q docs/two-hour-course/examples/E07_test_workflow.py docs/two-hour-course/examples/A02_test_callback_solution.py docs/two-hour-course/examples/A03_test_request_solution.py

# 以下两项需允许 127.0.0.1 临时端口，脚本结束后自动关闭。
PYTHONPATH=. .venv/bin/python docs/day-04/examples/E03_local_http_smoke.py
PYTHONPATH=. .venv/bin/python docs/day-05/examples/E01_ui_http_smoke.py
```

HTTP 练习的 [exercise.py](http-practice/exercise.py) 有意保留 TODO，完成后以 HTTP_PRACTICE_IMPL=exercise 运行；统一检查使用 [solution.py](http-practice/solution.py)。不要把参考实现已通过当作自己的作答已完成。

## 历史实施记录

正文中的“当前”“下一步”以该阶段记录时为准；接口后续有变化时，先回实施总览。以下测试数量属于历史验收，不是当前每次运行的预设结果。

| 记录 | 当时的范围 |
| --- | --- |
| [D1 基线](week-01-evidence.md) | 早期同步调用链、60 项测试、Git 核心基线 |
| [D2](day-02-evidence.md) | 契约、模式、阶段记录与结构化展示，163 项默认回归 |
| [D3](day-03-evidence.md) | 异步、期限、取消与资源隔离，232 项默认回归 |
| [D4](day-04-evidence.md) | 本地 API、准入与生命周期，287 项及本机 HTTP |
| [D5](day-05-evidence.md) | UI 接入 HTTP、未确认提交、fake 链路，live 未验证 |
| [D6](day-06-evidence.md) | 本地检查和事件日志；远程 CI 未运行 |
| [D7](day-07-evidence.md) | 两份干净 Linux/Python 3.12 环境、依赖快照、本机链路与重启 |

## 旧版静态导出

| 文件 | 版本与用途 |
| --- | --- |
| [Word 两小时课程](Multi-Agent_MVP_软件架构与Python源码精读_两小时课程.docx) | 早期同步版本的可编辑导出，可批注；未同步本次 Markdown 修订 |
| [PDF 项目解读](多智能体审核系统_项目解读.pdf) | 本次修订前的静态导出，不作为当前源码或启动步骤的依据 |

两份旧导出保留供历史对照，当前阅读使用对应 Markdown，不宣称二进制内容已更新或重新排版验收。需要共享当前运行说明时优先使用根 README、实施总览和本目录修订后的教程。

后续工作顺序：真实模型验收与质量评估 → 补交付证据 → 按需求加入最小本地 RAG；LangChain 按组件需求采用。它们不属于前四日重新实施的任务，详见 [后续路线](implementation-status.md#next-steps)。
