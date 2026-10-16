# D3 实施记录：异步请求、预算与取消

> 历史验收快照：正文的“当前”“下一步”、测试数量与接口描述以本阶段记录时为准。后续变更及现行状态见 [实施总览](implementation-status.md)，运行现有系统请按 [根 README](../README.md)。原命令含教学版本时，不直接覆盖现有源码。

日期：2026-10-16，Asia/Shanghai。承接 [D2 验收](day-02-evidence.md)，按照 [第三日计划](第三日计划任务.md) 实施。D3 工程验收完成；个人学习自测不代为勾选。

## 已实现

- `AsyncOpenAICompatibleClient` 使用 HTTPX 异步请求，保持模型、消息、认证与非流式响应契约；拒绝重定向，公开错误不包含供应商原文。客户端借用传输对象，由外层负责关闭。
- `run_review_async` 是唯一编排内核。同一审核内 A → C → J；独立审核可共享客户端与 `Semaphore(2)`，各自保留上下文和不可变记录。
- 三层预算：HTTPX 网络操作默认 60 秒、每次模型调用默认 60 秒、整次审核默认 150 秒。总截止时间只计算一次，包含等待名额，不逐阶段重置。超时分别记录 `network_timeout`、`model_timeout`、`total_timeout`。
- 取消传播 `CancelledError`；调用方持有独立的一次性 `ReviewRun` 读取进度或最终快照。正在执行阶段标记取消，未执行阶段跳过；有效回答保留、最终报告为空。清理完成后释放名额。
- 同步 `run_review` 仅包装异步内核，传入客户端必须实现异步 `complete`。`runtime.py` 为页面拥有一次事件循环和 HTTP 客户端生命周期；不跨事件循环缓存这些资源。
- D2 模式、报告校验、回调顺序、失败停止、部分结果与页面重跑行为保留。课堂替身迁移为异步 `complete` 或 `AsyncMock`。

旧同步 `OpenAICompatibleClient` 保留用于 HTTP 基础教程和补充练习；应用主路径不再调用它，也没有用线程包装同步网络调用。

## 实际验证

环境：Python 3.12，HTTPX 0.28.1、httpcore 1.0.9。运行依赖声明为 `httpx>=0.28,<0.29`。`pip check` 无依赖冲突。

在项目根目录执行：

```bash
.venv/bin/python -m pytest -q
# 232 passed in 2.86s

.venv/bin/python -m pytest -q docs/two-hour-course/examples/E07_test_workflow.py docs/two-hour-course/examples/A02_test_callback_solution.py docs/two-hour-course/examples/A03_test_request_solution.py
# 7 passed

HTTP_PRACTICE_IMPL=solution .venv/bin/python -m pytest -q docs/http-practice/test_exercises.py
# 29 passed

PYTHONPATH=. .venv/bin/python docs/day-03/examples/E04_integrated_reviews.py
```

D3 四个演示与课堂 E05/E06 均以退出码 0 完成。E01—E03 是标准库概念示例；E04 调用真实异步业务内核，验证并发成功、Critic 总预算耗尽、取消清理、取消后再次审核。

测试覆盖：两个审核交错推进而第三个等待；上下文隔离；排队期间超时与取消；单次预算与总预算；取消一份不影响共享客户端上的另一份；取消响应体读取后关闭响应；页面拥有的客户端在超时和取消后关闭；错误后的名额恢复；回调阻塞或客户端吞掉超时取消后不得发布逾期成功；无关 `TimeoutError` 不冒充预算耗尽；一次性运行容器与历史快照；嵌套事件循环明确拒绝。

## 使用边界

- 以上均为离线替身与受控传输测试，未验证真实模型连通性、真实网络超时或报告质量。
- Streamlit 同步适配层仍等待结果，没有用户停止按钮；每次调用独立管理资源，不提供跨会话统一容量限制。
- 取消是协作式机制，不能强制终止永不让出控制权的代码。同步回调需短小；预算到期后清理可能继续占用时间。
- 尚无 HTTP 服务、持久化、后台任务队列或跨进程协调；未引入数据库或 Docker。
- 当前改动在工作区，未创建 Git 提交。

下一步为 [D4 计划](第四日计划任务.md)：应用生命周期、严格 HTTP 契约、ReviewService 的统一准入与请求标识、201/422/409/429/502/504 映射。复用本日异步内核，不在路由重写业务逻辑。

后续更新：D4 已实现，见 [D4 实施记录](day-04-evidence.md)。异步内核新增可选 `total_deadline`，服务入口传入既定截止时间；不会重置总预算。
