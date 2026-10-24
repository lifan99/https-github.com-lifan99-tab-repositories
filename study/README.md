# Multi-Agent 项目学习

**日常从 [今天](今天.md) 继续。**2026-10-24 起，主线以 CS537/OSTEP 的执行与并发、UMass 的网络模型为基础，衔接异步、FastAPI 和测试；当前从 U1 的系统导论开始。前四阶段的完成记录保留，旧阶段 5 与 workflow lab 改为选做。

本次安排在本地生效；Notion“今天”尚未同步，保留为历史笔记来源。U1 原生 Notebook 已加入系统导论、Task/线程观察、条件通知实验和第 12 节独立 lab（含公开检查）；U3 拆成网络通信与数据校验两个连续课次。其余单元的讲义和 lab 随学习制作、核验。

| 要做什么 | 入口 |
| --- | --- |
| 当前任务、停止位置与实际完成证据 | [今天](今天.md) |
| 新主线的单元、目标、实验与必要参考 | [学习路线](学习路线.md) |
| 当前 U1 的完整讲义和运行示例 | [原生 Notebook](lectures/U1_async_execution.ipynb)、[Markdown 版](lectures/U1_async_execution.md) |
| 选做的旧项目数据流实验 | [workflow lab](workflow_lab/README.md) |
| 查看前四关的原始演示 | [入门示例](../examples/intro/) |
| 继续本人已经做过的练习 | [作答目录](practice/) |
| 练习同步客户端的请求、响应与错误 | [HTTP 练习册](练习册.md)、[作业与测试](../examples/http-practice/README.md) |
| 从项目上下文进入 LangChain | [手册](langchain/LangChain项目学习手册.md)、[示例](langchain/examples/README.md) |
| 核对源码与实际实现 | [工程文档](../docs/README.md)、[项目示例](../examples/README.md) |
| 追溯旧练习分区 | [原始快照](archive/daily-practice-2026-10-18.zip) |

通用 Python、算法和系统课在工作区 `~/ai-engineering/learning/`。当前主线与日常记录维护在本学习区；其他目录的历史日程不叠加执行。

需要运行本地实验时，使用项目解释器；具体文件以当前单元实验为准：

```bash
cd /home/fanli/ai-engineering/multi-agent/mvp
.venv/bin/python --version
```

`examples/` 保存提供的演示，`study/practice/` 保留本人作答。运行成功与本人完成验收分别记录。LangChain 的可选依赖使用该教程自己的环境，不安装进主项目环境。
