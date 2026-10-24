# 多 Agent 审核系统

本文是本项目的工程运行说明。项目配套学习保存在仓库的 study/，通用基础课位于工作区 learning/；目录边界见 [迁移说明](docs/目录迁移.md)。

一个基于 Python 3.12 和 Streamlit 的本地审核 MVP，用 Analyst、Critic、Judge 三个角色依次审核文本、代码、推理或技术方案，并展示每个阶段的回答。

```text
用户输入 → Analyst → Critic → Judge → 最终回答
```

当前版本采用异步工作流和 HTTPX OpenAI-compatible HTTP 接口，支持通过环境变量配置 Qwen 或 DeepSeek。每个角色使用独立系统提示词：Critic 收到原文和 Analyst 输出，Judge 收到原文及两个前序输出。

## 当前能力与验证状态

- 审核请求结束后显示各阶段角色、模型和回答；页面重跑时恢复当前会话结果。
- 输入为空白或超过 20,000 字符时，在模型调用前拒绝，不截断原文。
- 模型请求失败时停止后续角色，保留本次已经完成的回答。
- 处理 HTTP、连接、超时、断流和响应格式错误；Python 工作流回调异常停止后续阶段。UI 展示失败会保留已收到的结果，可重跑恢复。
- 供应商、端点、角色模型、网络操作超时、模型预算及审核总预算可配置；没有自动重试。
- 支持 `logic` / `evidence` 模式；Judge 报告严格验证 JSON、字段、枚举、原文引用和跨字段规则。
- 显示三阶段状态、结构化结论、问题、建议、引用与限制；非法 Judge 输出单独标注，不能作为最终报告。
- **2026-10-13 D1 离线核验：60 个测试通过**，涵盖工作流、客户端、配置、环境加载和 UI。测试不需要真实模型凭据。

**2026-10-16：D2—D4 已接入，D5 UI 已改为调用后端，D6 本地自动检查与日志已接入，339 项默认测试通过。** 多份审核在同一事件循环中共享客户端与名额时可以并发，单份审核仍按角色顺序执行。异步内核的总预算包含排队；HTTP 服务满载立即拒绝。取消保留已完成结果并释放名额。Streamlit 经 HTTP 调用后端并等待审核结束，尚无停止按钮；同一服务实例为页面请求统一管理容量。

本轮使用离线替身，真实模型连通性与审核质量未验证。两种模式都只评估输入材料，不会联网核验。FastAPI 服务已支持统一准入和错误映射；尚无数据库或跨重启历史恢复。完整状态见 [实施总览](docs/technical/工程状态.md)；最新证据见 [D7 实施记录](docs/archive/engineering/day-07-evidence.md)、[D6 实施记录](docs/archive/engineering/day-06-evidence.md)、[D5 实施记录](docs/archive/engineering/day-05-evidence.md)、[D4 实施记录](docs/archive/engineering/day-04-evidence.md)、[D3 实施记录](docs/archive/engineering/day-03-evidence.md)，前序记录见 [D2](docs/archive/engineering/day-02-evidence.md) 与 [D1](docs/archive/engineering/week-01-evidence.md)。

## 快速开始

以下命令适用于 Linux / WSL / Bash。在检出的仓库根目录执行，先安装依赖并运行离线测试：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-py312-linux.txt -e '.[test,dev]'
.venv/bin/python scripts/check.py
```

该精确版本清单已在 Linux x86_64 / Python 3.12 的干净环境复验，其他平台未做同等验证。统一检查包含 Ruff、本地文档链接、默认 pytest、课堂回归、HTTP 练习参考实现和依赖一致性检查。CI 使用同一入口，随后运行本机 fake HTTP/UI 演示；远程 CI 尚未执行。依赖安装需要访问包源；测试执行本身不调用外部模型。Windows PowerShell 的环境命令见 [入门教程](docs/technical/源码详解.md#s04)。

### 不使用模型凭据的流程演示

项目附带两个使用预置 fake 回答的教学脚本，可观察上下文传递与失败停止：

```bash
.venv/bin/python examples/core/E05_project_trace.py
.venv/bin/python examples/core/E06_project_failure.py
```

第一个输出 Analyst、Critic、Judge 的预置回答和上下文键；第二个模拟 Critic 失败，保留 Analyst 并停止 Judge。这些输出用于验证程序行为，不代表真实模型审核结果。Streamlit 本身无需模型凭据；连接显式 fake API 即可体验页面。

D2 的结构化报告成功与错误引用演示：

```bash
PYTHONPATH=. .venv/bin/python examples/contracts/E01_contract_review.py
PYTHONPATH=. .venv/bin/python examples/contracts/E01_contract_review.py --invalid-quote
```

### 启动本地 HTTP 服务（D4）

无凭据的离线服务：

```bash
REVIEW_EXECUTION_MODE=fake .venv/bin/python -m uvicorn review_system.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

另开终端：

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s http://127.0.0.1:8000/api/v1/reviews \
  -H 'Content-Type: application/json' \
  --data '{"request_id":"demo-001","original_input":"仅用内存保存历史。","review_mode":"logic"}'
```

`POST` 等审核完成后返回 201；报告结论可以是证据不足。fake 结果始终标明演示性质，不能用于判断材料质量。设置 `REVIEW_EXECUTION_MODE=live` 并配置凭据后使用真实模型；live 配置错误会阻止启动，不自动切换到 fake。`/docs` 提供接口文档。

当前服务必须使用单 worker：最多同时接受两份审核，执行中重复标识返回 409，新请求满载返回 429。模型失败为 502，三类预算失败为 504，非法请求为 422。标识只在执行期间去重，完成后重新提交会再次调用模型；没有历史查询或持久化幂等。Streamlit 已通过此接口提交审核；没有逐阶段推送，收到完整响应后统一展示各阶段。

真实本机 HTTP 的离线验收脚本（自动启动临时端口并关闭）：

```bash
PYTHONPATH=. .venv/bin/python examples/api/E03_local_http_smoke.py
```

### 配置后端并启动 UI

仅在使用 live 后端时需要模型凭据。复制 [配置模板](.env.example)，在本机 `.env` 中填写所选供应商的 API Key：

```bash
cp -n .env.example .env
```

`cp -n` 遇到已有 `.env` 时跳过复制，直接在本机编辑已有文件。应用启动时只加载项目根目录的 `.env`；已有环境变量优先，包括值为空的变量。切换供应商时设置 `REVIEW_PROVIDER` 并填写对应的 Key。

| 配置 | 用途 |
| --- | --- |
| `REVIEW_API_BASE_URL` | UI 使用的后端地址，默认 `http://127.0.0.1:8000` |
| `REVIEW_API_TIMEOUT_SECONDS` | UI 的 HTTP 操作等待时间，默认后端总预算加 30 秒；需大于总预算 |
| `REVIEW_EXECUTION_MODE` | 本地 API 的 `live`（默认）或显式 `fake` |
| `REVIEW_PROVIDER` | `qwen` 或 `deepseek`，默认 `qwen` |
| `QWEN_API_KEY` / `DEEPSEEK_API_KEY` | 所选供应商的凭据 |
| `QWEN_BASE_URL` / `DEEPSEEK_BASE_URL` | OpenAI-compatible API 根地址 |
| `QWEN_MODEL` / `DEEPSEEK_MODEL` | 所选供应商的默认模型 |
| `ANALYST_MODEL`、`CRITIC_MODEL`、`JUDGE_MODEL` | 可选的角色模型覆盖 |
| `REVIEW_TIMEOUT_SECONDS` | HTTPX connect/read/write/pool 操作超时，默认 60 秒 |
| `REVIEW_MODEL_TIMEOUT_SECONDS` | 一次模型调用预算，默认 60 秒 |
| `REVIEW_TOTAL_TIMEOUT_SECONDS` | 整次审核预算，包含等待名额，默认 150 秒 |

模板中的端点和模型名来自当前代码默认值；实际可用性需按账号、区域及供应商支持范围配置，并通过 live 调用验证。真实输入和前序回答会发送给所选供应商。

先启动上面的 fake 服务，或启动已配置凭据的 live 服务，再在另一个终端运行 UI：

```bash
REVIEW_API_BASE_URL=http://127.0.0.1:8000 .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

在终端显示的本地地址打开页面，填写材料并点击 Review。一次正常审核依次调用模型三次；结果仅保留在当前 Streamlit 会话中。页面明确标记 fake 输出；网络超时后不自动重试，同一未确认提交保留 request_id。该标识只防止执行中的重复请求，不能保证完成后的再次提交不会重新计费。

## 仓库结构

```text
.
├── app.py                   # Streamlit 入口与阶段展示
├── review_system/
│   ├── api.py               # FastAPI 工厂、生命周期与路由
│   ├── api_client.py        # UI 的 HTTP 客户端与响应核验
│   ├── api_models.py        # 严格请求与公开响应
│   ├── service.py           # 容量、活动标识与任务管理
│   ├── observability.py     # 只记录标识、阶段、状态、耗时和错误码
│   ├── fakes.py             # 显式离线演示客户端
│   ├── agents.py            # 三角色定义和独立提示词
│   ├── config.py            # 环境变量配置与校验
│   ├── environment.py       # 项目 .env 加载
│   ├── clients.py           # 模型客户端协议与 HTTP 调用
│   ├── contracts.py         # 请求、报告、引用校验与阶段记录
│   ├── runtime.py           # Python 同步入口的循环与 HTTP 生命周期
│   └── workflow.py          # 顺序、上下文、结果及错误传播
├── scripts/check.py         # 本地与 CI 共用离线检查
├── .github/workflows/       # 自动回归配置
├── tests/                   # 默认离线回归测试
├── docs/                    # 项目说明、技术文档与工程证据
├── examples/                # 本项目的教学与验证示例
├── study/                   # 项目学习路线、任务、作答与定制教程
├── AGENTS.md                # 工程约束
├── requirements-py312-linux.txt # 已验证的依赖版本快照
├── pyproject.toml           # Python 依赖与测试配置
├── .env.example             # 不含凭据的配置模板
├── .gitignore               # 排除本地配置与生成文件
└── .gitattributes           # 文本换行和 Word 文件属性
```

工作流依赖 `AsyncLLMClient.complete(model=..., messages=...)`，通过 `await` 获取文本。`run_review_async` 是唯一业务内核；`run_review` 是供同步脚本调用的薄封装，传入的客户端也必须提供异步 `complete`。本地 Python 脚本仍可通过 `runtime.run_review_with_settings` 管理一次事件循环和模型 HTTP 客户端；UI 现经 `api_client.submit_review` 调用后端。旧 `OpenAICompatibleClient` 仅保留供 HTTP 基础教程与练习使用。

模型错误转换为携带阶段、已完成回答及记录的 `WorkflowError`。任务取消重新抛出 `CancelledError`，调用方可通过每份审核独立的 `ReviewRun` 查看最后快照。Judge 输出经 `parse_final_review` 校验，全部阶段和回调成功后才发布 `result.record.final_review`；`result.final_response` 保留原始 JSON。

D3 的实际业务内核离线演示（并发、总期限、取消及取消后复用）：

```bash
PYTHONPATH=. .venv/bin/python examples/async/E04_integrated_reviews.py
```

## 文档与学习入口

[项目文档导航](docs/README.md)汇总源码、接口与工程证据；[项目学习入口](study/README.md)组织阶段路线、[今天的任务与完成记录](study/今天.md)、作业与本人作答；[示例索引](examples/README.md)用于离线演示。

整个工作区从 `~/ai-engineering/README.md` 进入，通用基础课在 `~/ai-engineering/learning/`。普通项目检查包含 `study/` 的本地链接，不依赖仓库外的基础课程。运行 `.venv/bin/python scripts/check.py --include-personal` 可一并检查工作区导航、基础课程、求职与独立资料，以及三道已有 Python 练习。

## 版本管理

源码、测试、文档和 `.env.example` 纳入 Git；`.env` 及其变体、虚拟环境、缓存、临时目录和构建产物由 `.gitignore` 排除。API Key 从环境读取，配置对象的常规表示及显示的供应商错误省略凭据。

D1 历史核心代码基线为 `334e350`。当前交付包含 D2—D7 的异步工作流、本地 API、HTTP UI、离线回归和配套学习材料，统一检查命令为 `.venv/bin/python scripts/check.py`。真实模型联调、远程 CI 与复现验收的实际状态见[实施总览](docs/technical/工程状态.md)；历史日记录保留当时的验证范围。
