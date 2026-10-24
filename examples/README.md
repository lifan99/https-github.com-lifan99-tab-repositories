# 项目配套示例

返回 [项目文档导航](../docs/README.md)。以下命令从项目根目录执行，使用项目环境；示例不要求真实模型凭据。

| 目录 | 主题 | 配套材料 |
| --- | --- | --- |
| [intro/](intro/) | 前四关的上下文、函数、顺序与失败处理演示 | [项目学习路线](../study/学习路线.md) |
| [core/](core) | 对象、客户端协议、工作流、测试与页面状态 | [源码详解](../docs/technical/源码详解.md) |
| [contracts/](contracts) | 报告与原文引用 | [数据契约](../docs/technical/数据契约.md) |
| [async/](async) | 并发、期限、取消与清理 | [异步](../docs/technical/异步.md) |
| [api/](api) | HTTP 契约、准入与生命周期 | [服务](../docs/technical/服务.md) |
| [ui/](ui) | 页面与本地 HTTP 交互 | [项目手册](../docs/项目手册.md) |
| [HTTP 练习](http-practice/README.md) | 作业模板、离线测试与参考实现 | [HTTP 基础](../docs/technical/HTTP基础.md) |

```bash
PYTHONPATH=. .venv/bin/python examples/core/E05_project_trace.py
```

本人项目作答与定制 LangChain 教程见 [项目学习区](../study/README.md)。通用 Python 独立练习位于工作区 `~/ai-engineering/learning/python/`。项目统一检查覆盖本目录的课堂回归和 HTTP 参考实现。
