# D4 实施记录：本地 HTTP 服务与任务生命周期

> 历史工程档案：日期与结果保留；2026-10-17 整理时仅调整材料链接和示例路径。这里的 D 编号不是当前学习进度。

> 历史验收快照：正文的“当前”“下一步”、测试数量与接口描述以本阶段记录时为准。后续变更及现行状态见 [实施总览](../../technical/工程状态.md)，运行现有系统请按 [根 README](../../../README.md)。原命令含教学版本时，不直接覆盖现有源码。

日期：2026-10-16，Asia/Shanghai。承接 [D3](day-03-evidence.md)，按 [第四日计划](../../technical/服务.md#practice) 完成工程验收。个人学习自述与勾选保留给学习者。

## 已实现的调用链

```text
HTTP 请求 → ReviewBody 严格校验 → ReviewService 准入与任务管理
  → run_review_async → AsyncOpenAICompatibleClient / 显式 DemoClient
  → 已校验报告与部分结果 → 公开响应 DTO → HTTP JSON
```

`api.py` 提供应用工厂、lifespan、健康与审核路由；`api_models.py` 定义严格输入与公开输出；`service.py` 管理活动标识、容量、运行标识和子任务。HTTP/UI 类型不进入 Service 或异步内核。

启动阶段才加载配置。live 配置错误导致启动失败，不降级为 fake；显式 fake 不需要 Key，不创建供应商 HTTP 传输。关闭时先拒绝准入，再取消并等待审核，最后由资源所有者关闭客户端。两份独立应用不共享服务状态。

单事件循环内准入检查与登记之间没有 await：关闭返回 503；活动标识重复优先返回 409；新请求遇到容量 2 已满返回 429。未获准入不产生审核标识或模型调用。完成、失败、取消后释放本次标识；结束后复用标识会创建新 review_id 并重新执行。

Service 入口建立总截止时间，通过 `total_deadline` 传给 D3 内核，包括任务调度等待，不在子任务开始时重置预算。HTTP 入口满载立即拒绝，不重复获取 D3 排队示例里的信号量。

## 公开接口

| 场景 | HTTP | 结果 |
| --- | --- | --- |
| GET /healthz | 200 | status=ok 与 execution_mode，不调用模型 |
| POST /api/v1/reviews 成功 | 201 | 三阶段回答、阶段状态、最终报告、request_id/review_id |
| 非法 JSON、字段、标识、输入 | 422 | invalid_request；无原文回显、审核标识或模型调用 |
| 执行中重复标识 | 409 | duplicate_request |
| 新请求遇到本地满载 | 429 | capacity_exceeded |
| 供应商错误、非法 Judge 报告 | 502 | model_error / invalid_output；保留有效部分结果 |
| 三层超时 | 504 | network_timeout / model_timeout / total_timeout |
| 内部代码或响应缺陷 | 500 | internal_error；固定安全信息 |
| 服务关闭后准入 | 503 | service_unavailable |

错误正文先经过 DTO 校验。取消继续传播，不承诺连接已断开时还可返回正文。框架 404/405 保留；审核端点非法 JSON 字节产生的框架 400 统一为契约规定的 422。上游 429 归入 502/model_error，本地满载才返回 429。

## 实际验证

Python 3.12；FastAPI 0.143.2、Pydantic 2.14.1、Starlette 1.7.0、Uvicorn 0.54.0、HTTPX 0.28.1。依赖范围见 pyproject.toml；`pip check` 无冲突。

```bash
.venv/bin/python -m pytest -q
# 287 passed in 3.38s

PYTHONPATH=. .venv/bin/python examples/api/E03_local_http_smoke.py
# 201 succeeded; three responses; execution_mode=fake
# 422 invalid_request; no review_id or model results
# 504 model_timeout; Analyst preserved; no final report
# Loopback servers stopped; review tasks collected.
```

默认回归增加 Service 与真实路由测试，包括并发 409/429、父请求取消、子任务启动前取消、容量恢复、上下文隔离、同标识重跑、总期限跨调度传递、真实计时器、非法 UTF-8、错误清理、lifespan 关闭顺序与应用隔离。

默认接口测试使用 ASGITransport 并显式进入 lifespan，不需要监听端口。另行使用 TestClient 上下文验证健康 200、审核 201；本机受限沙箱的跨线程唤醒挂起，15 秒受限重试在允许本地执行的环境通过。Starlette 对 HTTPX TestClient 的弃用警告如实保留，默认回归不依赖该桥接。

E03 则通过 Uvicorn 在 127.0.0.1 临时端口真实监听，HTTPX 经本机网络得到上述 201/422/504。普通沙箱禁止 socket，获准本地监听后通过；脚本自动关闭服务。两种验证范围分别记录，没有将进程内测试冒充真实监听。

## 启动和边界

```bash
REVIEW_EXECUTION_MODE=fake .venv/bin/python -m uvicorn review_system.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

接口文档在 `/docs`。单 worker 和本机监听是当前运行前提；没有鉴权、多进程容量协调、持久化幂等或历史查询。fake 报告固定标明未审核真实材料。

未进行真实模型调用，未验证供应商可用性、报告质量或真实 TCP 断连触发服务取消。当前测试验证的是 handler Task 取消与清理。尚未修改 UI 为 HTTP 调用方，下一项为 D5。未引入数据库、Docker，未创建 Git 提交。

实现参照 [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/) 与 [错误处理](https://fastapi.tiangolo.com/tutorial/handling-errors/)；容量和响应映射遵循本项目的 D4 契约。
