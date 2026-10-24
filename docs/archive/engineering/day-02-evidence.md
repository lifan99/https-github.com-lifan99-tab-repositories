# D2 实施记录：结构化报告与阶段状态

> 历史工程档案：日期与结果保留；2026-10-17 整理时仅调整材料链接和示例路径。这里的 D 编号不是当前学习进度。

> 历史验收快照：正文的“当前”“下一步”、测试数量与接口描述以本阶段记录时为准。后续变更及现行状态见 [实施总览](../../technical/工程状态.md)，运行现有系统请按 [根 README](../../../README.md)。原命令含教学版本时，不直接覆盖现有源码。

日期：2026-10-16，Asia/Shanghai。依据 [D2 计划](../../technical/数据契约.md#practice) 与 [契约 v1 阅读材料](../../technical/数据契约.md)，从 D1 同步实现增量扩展。

## 结果

D2 工程验收完成。Judge 必须返回符合契约的 JSON 报告；错误引用、重复字段、非标准常量、字段类型或跨字段冲突均不能发布最终报告。两种审核模式、三阶段状态、部分结果和 UI 重跑已接入。个人学习掌握程度不由自动测试代替。

本轮不调用真实模型，也不读取或展示真实凭证。live 连通性与输出质量未验证。已有文档与 HTTP 练习保留，未创建 Git 提交。

## 改动与证据

| 计划项 | 实现与验收 |
| --- | --- |
| T1 基线 | 开始前默认测试 60 项通过；核对同步工作流、客户端、页面和既有改动 |
| T2 契约样例 | [合法报告](../../../tests/fixtures/d2/valid_report.json)；契约测试在此基础上构造缺字段、枚举、引用、布尔坐标与跨字段冲突 |
| T3 纯校验 | [contracts.py](../../../review_system/contracts.py)：请求、严格 JSON、完整字段、引用与结论一致性；[契约测试](../../../tests/test_contracts.py) |
| T4 阶段状态 | 不可变 `StageRecord/ReviewRecord`；成功、模型失败、契约失败、回调失败的快照与 skipped 后续阶段 |
| T5 工作流 | [workflow.py](../../../review_system/workflow.py)：新增 `review_mode`；Judge 校验在加入有效回答前；错误携带 `record`；提示词中的完整示例经实际校验 |
| T6 页面 | [app.py](../../../app.py)：模式、状态、报告字段、未通过校验的原始输出；AppTest 覆盖成功后失败、重跑和旧结果清理 |
| T7 迁移 | 既有调用顺序、原文、前序输出、调用次数、回调保留、协议错误断言继续保留；课堂成功替身改为合法报告 |
| T8 记录 | 本文及新的离线报告演示；原 D1 证据保留为历史快照 |

D2 没有新增运行依赖。`MAX_INPUT_CHARS` 移入契约模块，`workflow` 继续导出该名称以兼容既有调用。报告里的列表转换为元组，使成功快照不受外部列表修改影响。

## 实际验证

在 `mvp` 根目录执行：

```bash
.venv/bin/python -m pytest -q
# 163 passed in 1.61s

.venv/bin/python -m pytest -q examples/core/E07_test_workflow.py examples/core/A02_test_callback_solution.py examples/core/A03_test_request_solution.py
# 7 passed in 0.05s

PYTHONPATH=. .venv/bin/python examples/core/E05_project_trace.py
PYTHONPATH=. .venv/bin/python examples/core/E06_project_failure.py
PYTHONPATH=. .venv/bin/python examples/contracts/E01_contract_review.py
PYTHONPATH=. .venv/bin/python examples/contracts/E01_contract_review.py --invalid-quote
```

四个演示均退出码 0。E05 显示三阶段各自上下文，新增 `review_mode`；E06 显示 `Critic 1`，保留 Analyst。

D2 合法示例：原文 `仅用内存保存记录，重启后历史仍在。`，报告引用 `[9:16]` 为 `重启后历史仍在`；结论 `needs_revision`；阶段全部 `succeeded`；调用 3 次。

D2 非法示例：将同一引用的 `start` 改为 8；公开错误为 `Judge failed: report.findings[0].quote: must match original_input[start:end].`；保留 2 份有效回答；状态为 `succeeded / succeeded / failed`；最终报告为空；调用仍为 3 次，无隐藏修复请求。

## 当前接口与兼容变化

```python
result = run_review(
    original_input, client, analyst_model="a", critic_model="c", judge_model="j",
    review_mode="evidence",
)
report = result.record.final_review
```

`final_response` 仍返回 Judge 原始字符串，但它现在是已验证的 JSON。旧的成功替身 `"J"`、`"Verdict"` 必须升级为合法报告。失败时读取 `WorkflowError.record` 与 `completed`；Judge 契约失败的原始文本只在失败阶段记录中。

三阶段和回调全部成功后才设置 `final_review`。Judge 回调失败虽然保留三份有效回答，仍没有可发布的最终报告。模型错误与回调错误继续使用既有公共错误语义，`KeyboardInterrupt` 继续传播。

## 后续

下一项为 [D3 异步、期限与取消](../../technical/异步.md#practice)：迁移网络 I/O，区分网络超时、模型期限与总期限，并验证并发隔离及取消清理。D4 依赖 D3；数据库与 Docker 仍受 AGENTS.md 限制。

2026-10-16 后续更新：D3 已完成，见 [D3 实施记录](day-03-evidence.md)。上面的数量与接口说明是 D2 验收快照；当前同步入口接受异步客户端。
