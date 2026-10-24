# D5 实施记录：UI 接入后端

> 历史工程档案：日期与结果保留；2026-10-17 整理时仅调整材料链接和示例路径。这里的 D 编号不是当前学习进度。

> 历史验收快照：正文的“当前”“下一步”、测试数量与接口描述以本阶段记录时为准。后续变更及现行状态见 [实施总览](../../technical/工程状态.md)，运行现有系统请按 [根 README](../../../README.md)。原命令含教学版本时，不直接覆盖现有源码。

日期：2026-10-16，Asia/Shanghai。依据第一周规划中的 D5 项及 [D4 后续安排](day-04-evidence.md)。UI 与离线链路验收完成；**live 验收未完成**，本机 Qwen、DeepSeek 均未配置凭据。未读取或展示凭据内容，未发出付费模型请求。

## 行为变化

页面只经 `api_client.submit_review` 提交 `request_id/original_input/review_mode`；模型凭据与角色配置由后端管理。API 根地址默认 `http://127.0.0.1:8000`；UI HTTP 操作超时默认后端总预算加 30 秒，并要求大于同一环境声明的服务总预算。独立部署时需人工协调双方配置，此校验不能发现另一台机器的实际设置。

D4 接口不推送中间阶段，因此 UI 在响应回来后统一展示各阶段。失败保留后端返回的有效回答和状态；新提交清理旧报告。页面重跑不重新发请求。展示失败也不会丢失已收到的结果，重跑可恢复展示。

成功响应核验请求标识、审核 UUID、阶段顺序、原始回答与阶段记录的一致性，并使用 D2 校验器检查 Judge JSON、原文引用及其与 final_review 的一致性。非法响应不能作为最终报告。前后端共享公开错误映射，避免状态码漂移。

fake 标识来自后端响应并在页面明显展示，不根据 UI 环境猜测。API 客户端不跟随重定向、不发送供应商凭据、不自动重试，错误信息不包含网络异常或服务器正文细节。

## 未确认结果和重复提交

网络超时、协议失败等情况下没有可信的完成结果，页面保留本次标识。同样材料和模式再次提交沿用标识；409 继续保留。确认完成或其他明确拒绝后，下次提交使用新标识。修改材料或模式时创建新标识。

这一规则只能让服务识别仍在执行的重叠提交。前次已结束但响应丢失时，重试仍可能再调用模型；页面明确告知这一边界。当前没有取消端点、自动重试、结果找回或“只计费一次”保证。

## 实际验证

```bash
.venv/bin/python -m pytest -q
# 327 passed in 3.26s

PYTHONPATH=. .venv/bin/python examples/ui/E01_ui_http_smoke.py
# UI -> HTTP -> API -> A/C/J: success; fake badge; rerun sends no request
# UI -> HTTP -> API -> Critic failure: partial result preserved; old report cleared
# Local API stopped; all owned review tasks collected.
```

默认 AppTest 经模拟 HTTP 传输进入真实 API、Service、异步内核，再由替身供应商回答。新增 API 客户端测试覆盖响应关联、结构、报告与摘录、状态码、网络异常、重定向、等待预算和客户端关闭。页面测试覆盖无凭据 fake、成功后失败、错误引用、展示失败恢复、重跑、请求标识复用及更换。

E01 使用真实 Uvicorn 本机临时端口，AppTest 的 HTTP 客户端未经 mock，供应商客户端显式注入 fake。第一份审核 3 次模型调用成功；第二份 Critic 失败后共 5 次调用，Judge 不启动；重跑调用次数不变。服务自动关闭。AppTest 是页面执行测试，没有声称人工浏览器视觉验收或真实模型审核质量已验证。

## 启动

终端 1：

```bash
REVIEW_EXECUTION_MODE=fake .venv/bin/python -m uvicorn review_system.api:create_app --factory --host 127.0.0.1 --port 8000 --workers 1
```

终端 2：

```bash
REVIEW_API_BASE_URL=http://127.0.0.1:8000 .venv/bin/python -m streamlit run app.py --server.address 127.0.0.1
```

live 待在本机 `.env` 配置真实供应商凭据后验证；不要将凭据写入测试或记录。D6 可继续完成离线自动回归与日志，不受此项阻塞。
