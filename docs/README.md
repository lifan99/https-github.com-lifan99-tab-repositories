# 文档索引

应用运行方式和当前能力以根目录 [README](../README.md) 为入口；工程限制以 [AGENTS.md](../AGENTS.md) 为准。

| 材料 | 用途 |
| --- | --- |
| [D1 基线记录](week-01-evidence.md) | 查看实际测试、调用链、错误出口、Git 基线及 D2—D7 状态 |
| [固定审核输入](samples/d1-logic-proposal.txt) | 复用短技术方案进行回归或演示 |
| [从零手撕多智能体审查项目](从零手撕多智能体审查项目.md) | 学习环境、角色、客户端、工作流、UI、测试及排错 |
| [两小时源码精读讲义](two-hour-course/完整讲义.md) | 按十个模块学习项目结构和 Python 基础 |
| [可编辑 Word 讲义](Multi-Agent_MVP_软件架构与Python源码精读_两小时课程.docx) | 在 Word 中阅读、批注和编辑课程 |
| [课堂示例](two-hour-course/examples/) | 独立概念练习、项目 fake 路径和参考答案 |

## 课堂示例的运行方式

在仓库根目录安装 `.[test]` 后执行。所有模型相关课堂示例均使用 fake/Mock，不需要真实模型凭据。

```bash
# 成功路径和 Critic 失败路径。
.venv/bin/python docs/two-hour-course/examples/E05_project_trace.py
.venv/bin/python docs/two-hour-course/examples/E06_project_failure.py

# 显式运行课堂额外测试；它们不属于默认 tests/ 集合。
.venv/bin/python -m pytest -q docs/two-hour-course/examples/E07_test_workflow.py docs/two-hour-course/examples/A02_test_callback_solution.py docs/two-hour-course/examples/A03_test_request_solution.py

# 观察 Streamlit 页面重跑和会话状态。
.venv/bin/python -m streamlit run docs/two-hour-course/examples/E08_streamlit_counter.py
```

课程保留编写日期和历史源码节选。测试数量、配置默认值和能力描述应结合当前代码及最新核验记录阅读；教学中的 asyncio 例子不表示应用已经实现异步网络调用。
