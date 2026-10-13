# 多 Agent 审核系统

一个基于 Python 3.12 和 Streamlit 的本地审核 MVP，用 Analyst、Critic、Judge 三个角色依次审核文本、代码、推理或技术方案，并展示每个阶段的回答。

```text
用户输入 → Analyst → Critic → Judge → 最终回答
```

当前版本采用同步工作流和 OpenAI-compatible HTTP 接口，支持通过环境变量配置 Qwen 或 DeepSeek。每个角色使用独立系统提示词：Critic 收到原文和 Analyst 输出，Judge 收到原文及两个前序输出。

## 当前能力与验证状态

- 每阶段完成后显示角色、模型和回答；页面重跑时恢复当前会话结果。
- 输入为空白或超过 20,000 字符时，在模型调用前拒绝，不截断原文。
- 模型请求失败时停止后续角色，保留本次已经完成的回答。
- 处理 HTTP、连接、超时、断流和响应格式错误；普通展示回调异常也会停止流程并保留当前阶段结果。
- 供应商、端点、角色模型及 socket 超时可配置；没有自动重试。
- **2026-10-13 D1 离线核验：60 个测试通过**，涵盖工作流、客户端、配置、环境加载和 UI。测试不需要真实模型凭据。

本次环境缺少可用凭据，真实模型连通性与审核质量尚未验证。当前没有异步服务、FastAPI、结构化报告 Schema、数据库或跨重启历史恢复。完整证据与 D2—D7 状态见 [D1 基线记录](docs/week-01-evidence.md)。

## 快速开始

以下命令适用于 Linux / WSL / Bash。在检出的仓库根目录执行，先安装依赖并运行离线测试：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest -q
```

依赖安装需要访问包源；测试执行本身不调用外部模型。Windows PowerShell 的环境命令见 [入门教程](docs/从零手撕多智能体审查项目.md#s04)。

### 不使用模型凭据的流程演示

项目附带两个使用预置 fake 回答的教学脚本，可观察上下文传递与失败停止：

```bash
.venv/bin/python docs/two-hour-course/examples/E05_project_trace.py
.venv/bin/python docs/two-hour-course/examples/E06_project_failure.py
```

第一个输出 Analyst、Critic、Judge 的预置回答和上下文键；第二个模拟 Critic 失败，保留 Analyst 并停止 Judge。这些输出用于验证程序行为，不代表真实模型审核结果。Streamlit 应用仍需要配置真实模型凭据。

### 配置模型并启动 UI

复制 [配置模板](.env.example)，在本机 `.env` 中填写所选供应商的 API Key：

```bash
cp .env.example .env
```

应用启动时只加载项目根目录的 `.env`；已有环境变量优先，包括值为空的变量。切换供应商时设置 `REVIEW_PROVIDER` 并填写对应的 Key。

| 配置 | 用途 |
| --- | --- |
| `REVIEW_PROVIDER` | `qwen` 或 `deepseek`，默认 `qwen` |
| `QWEN_API_KEY` / `DEEPSEEK_API_KEY` | 所选供应商的凭据 |
| `QWEN_BASE_URL` / `DEEPSEEK_BASE_URL` | OpenAI-compatible API 根地址 |
| `QWEN_MODEL` / `DEEPSEEK_MODEL` | 所选供应商的默认模型 |
| `ANALYST_MODEL`、`CRITIC_MODEL`、`JUDGE_MODEL` | 可选的角色模型覆盖 |
| `REVIEW_TIMEOUT_SECONDS` | socket 阻塞操作超时，默认 60 秒；不等于全审核总期限 |

模板中的端点和模型名来自当前代码默认值；实际可用性需按账号、区域及供应商支持范围配置，并通过 live 调用验证。真实输入和前序回答会发送给所选供应商。

```bash
.venv/bin/python -m streamlit run app.py
```

在终端显示的本地地址打开页面，填写材料并点击 Review。一次正常审核依次调用模型三次；结果仅保留在当前 Streamlit 会话中。

## 仓库结构

```text
.
├── app.py                   # Streamlit 入口与阶段展示
├── review_system/
│   ├── agents.py            # 三角色定义和独立提示词
│   ├── config.py            # 环境变量配置与校验
│   ├── environment.py       # 项目 .env 加载
│   ├── clients.py           # 模型客户端协议与 HTTP 调用
│   └── workflow.py          # 顺序、上下文、结果及错误传播
├── tests/                   # 默认离线回归测试
├── docs/                    # 基线证据、学习资料与固定样例
├── AGENTS.md                # 工程约束
├── pyproject.toml           # Python 依赖与测试配置
├── .env.example             # 不含凭据的配置模板
├── .gitignore               # 排除本地配置与生成文件
└── .gitattributes           # 文本换行和 Word 文件属性
```

工作流只依赖 `LLMClient.complete(model=..., messages=...)`。客户端返回非空文本，模型调用失败时抛出 `LLMError`；工作流转换为带阶段名与已完成回答的 `WorkflowError`。结果 dataclass 保存角色输出文本，JSON 用于传递上下文；当前尚未实现审核报告的字段级 Schema 校验。

## 文档与学习入口

- [文档索引](docs/README.md)：按运行、核验和学习用途选择材料。
- [从零手撕多智能体审查项目](docs/从零手撕多智能体审查项目.md)：环境、源码、测试和排错入门。
- [两小时源码精读讲义](docs/two-hour-course/完整讲义.md)：结合独立例子理解架构与 Python。
- [可编辑 Word 讲义](docs/Multi-Agent_MVP_软件架构与Python源码精读_两小时课程.docx)。
- [D1 基线记录](docs/week-01-evidence.md)：真实测试结果、调用链、fake 观察和后续工程状态。
- [固定审核输入](docs/samples/d1-logic-proposal.txt)：供后续回归与演示复用。

课程中的测试结果和源码节选属于其标注版本；再次验证时以当前源码和实际终端输出为准。默认 pytest 只运行 `tests/`，课程练习需要显式指定文件。

## 版本管理

源码、测试、文档和 `.env.example` 纳入 Git；`.env` 及其变体、虚拟环境、缓存、临时目录和构建产物由 `.gitignore` 排除。API Key 从环境读取，配置对象的常规表示及显示的供应商错误省略凭据。

当前核验的核心代码基线为 `334e350`。后续文档整理提交保留这份证据，不代表 D2—D7 或真实模型调用已经完成。
