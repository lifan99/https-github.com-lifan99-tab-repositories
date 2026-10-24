# Workflow Lab：追踪一次三角色评审

2026-10-24 调整：本 lab 已改为选做。当前主线见 [学习路线](../学习路线.md)，是否完成本 lab 不影响学习异步与 FastAPI。

预计 25–35 分钟。目标是核查刚学过的 workflow；这属于看过讲解后的练习，不能据此认定已经独立掌握整个项目。

本 lab 使用离线假模型，无需 API Key。只修改同目录的 `exercise.py` 中标有 TODO 的函数。完成后把预测、输出和解释发到聊天中；这里不自动更新“今天.md”的阶段状态。

## 1. 先预测（约 5 分钟）

先完成这一项，再写代码或运行验收检查。

本次原文是 `Use a shared cache.`，模式是 `logic`。假模型按角色固定返回：

| 角色 | 固定回答 |
| --- | --- |
| Analyst | `Check cache invalidation.` |
| Critic | `Consider stale data.` |
| Judge | `Revise the proposal.` |

规则：每个角色收到原文、模式和所有已完成角色的回答。请求材料中的键使用项目里的名字：`original_input`、`review_mode`、`analyst_output`、`critic_output`、`judge_output`；只在相应材料已经产生时加入。每个角色只调用一次，顺序为 Analyst、Critic、Judge。

写下三个角色**被调用之前**各自收到的完整材料字典，并回答：

1. Critic 收到的 `analyst_output` 与 Critic 自己返回的回答，各是什么？
2. 只把假模型的 Analyst 回答改为 `Check eviction.`，其他预设保持不变：哪些后续请求中的值会改变？Critic 和 Judge 的固定返回值会改变吗？

保留最初的预测，验证后在旁边写修正，不覆盖原预测。

## 2. 实现一个小型 workflow（约 15–20 分钟）

打开同目录的 `exercise.py`，只实现：

```python
run_workflow(original_input, review_mode, call_model)
```

### 输入与输出合同

- `original_input` 和 `review_mode` 都是字符串。本练习允许空原文，照原样传递；不实现输入校验。
- `call_model(role, request_text)` 是已经提供的调用接口：`role` 为角色名称，`request_text` 为包含本轮材料的 JSON 字符串；它返回一个字符串回答。
- 请求材料遵循第 1 项的规则，不加入额外字段。
- 返回值是按调用顺序排列的 `(角色名称, 回答)` 二元组列表，包含三个角色。
- 假定三次调用均成功；异常、超时、async、system prompt 和 Judge 报告解析不在本 lab 的验收范围内。
- 每次运行应独立，不继承上次运行的材料。原文或回答含中文时，JSON 解析后应保留原值。
- workflow 应使用传入的 `call_model`，能够换成另一套固定回答；不要把本页的回答写进 workflow。

运行练习：

```bash
cd /home/fanli/ai-engineering/multi-agent/mvp
.venv/bin/python study/workflow_lab/exercise.py
```

文件最初会提示函数尚未实现，这是练习的起点。实现后，输出分为 `REQUESTS`（记录的请求）和 `RESPONSES`（收到的回答）两组；这两组是运行后的分类展示，不是实际执行时间线。

对照第 1 项的预测，再运行公开验收检查：

```bash
.venv/bin/python -m pytest study/workflow_lab/check_lab.py -q
```

检查文件包含预期结果，建议先保留自己的实现，再阅读失败信息。原项目默认的 `pytest` 只检查 `tests/`，不会自动收集这个尚待完成的 lab。

## 3. 迁移题：材料改变之后（约 5–10 分钟）

下面是独立的小片段，不是第 2 项的实现提示。先预测结果，再自行运行核对。

```python
import json

context = {"original_input": "Plan X", "review_mode": "logic"}
request_text = json.dumps(context, ensure_ascii=False)
context["original_input"] = "Plan Y"

print(json.loads(request_text)["original_input"])
print(context["original_input"])
```

回答：

1. 两行分别打印什么？解释依据。
2. 假设紧接着执行 `call_model("Analyst", request_text)`，模型收到哪份原文？
3. 用自己的话解释，你在第 2 项中如何保证每一轮请求包含该轮应有的材料。

## 提交与判断标准

提交这四样即可：

1. 第 1 项的原始预测，以及验证后的修正。
2. `run_workflow` 的实现。
3. 练习运行输出和验收检查结果。
4. 第 3 项的预测、实际输出和解释。

评价分开看三部分：

| 核查点 | 所需证据 |
| --- | --- |
| 数据流 | 能列出三轮请求，并区分请求材料与返回值 |
| 实现 | 公开检查通过，能处理替换回答、不同原文和连续运行 |
| 机制解释 | 能说明请求文本与材料字典之间的关系，并解释迁移题 |

测试通过说明实现满足这些公开案例；解释尚未确认时，状态仍是“已运行，解释待确认”。遇到卡点可以提交当前代码和报错，不必一次完成全部。
