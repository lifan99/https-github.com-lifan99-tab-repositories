# D7 实施记录：干净环境复现与重启演示

> 历史工程档案：日期与结果保留；2026-10-17 整理时仅调整材料链接和示例路径。这里的 D 编号不是当前学习进度。

> 历史验收快照：正文的“当前”“下一步”、测试数量与接口描述以本阶段记录时为准。后续变更及现行状态见 [实施总览](../../technical/工程状态.md)，运行现有系统请按 [根 README](../../../README.md)。原命令含教学版本时，不直接覆盖现有源码。

日期：2026-10-16，Asia/Shanghai。完成当前约束下的离线复现；没有数据库或 Docker，没有替代 live 验收。当前工作区未提交，本轮验证的是完整源码副本，不宣称已经验证某个新 Git 提交的干净检出。

## 环境与依赖

实际环境：CPython 3.12.3、Linux x86_64。首次在不含 `.env`、`.git`、旧虚拟环境和缓存的独立源码副本中安装 `.[test,dev]`；由该环境导出 [49 项精确依赖](../../../requirements-py312-linux.txt)。随后新建第二个空虚拟环境，使用这份清单安装项目，核对全部 49 项版本一致。

| 依赖 | 复现版本 |
| --- | --- |
| Streamlit | 1.66.0 |
| FastAPI / Starlette | 0.143.2 / 1.8.0 |
| Pydantic | 2.14.1 |
| HTTPX / Uvicorn | 0.28.1 / 0.54.0 |
| pytest / Ruff | 9.1.1 / 0.17.1 |

清单不包含本机可编辑路径、凭据或仓库地址。它是 Linux/Python 3.12 的版本快照，不是跨平台求解锁文件，也没有包哈希、Python 二进制或构建隔离环境的完全锁定。版本固定的作用和边界参照 [pip repeatable installs](https://pip.pypa.io/en/latest/topics/repeatable-installs/)；`pip freeze` 本身只记录已安装版本，见 [官方说明](https://pip.pypa.io/en/stable/cli/pip_freeze/)。

## 可重复执行的命令

在完整项目源码目录内创建新虚拟环境：

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements-py312-linux.txt -e '.[test,dev]'
.venv/bin/python scripts/check.py

PYTHONPATH=. .venv/bin/python examples/api/E03_local_http_smoke.py
PYTHONPATH=. .venv/bin/python examples/ui/E01_ui_http_smoke.py
.venv/bin/python scripts/smoke_restart.py
```

安装需要包源网络；默认检查不需要模型凭据或模型网络。后三个演示需要允许本机监听。API 工厂默认 live；上述演示显式使用 fake，不会因缺 Key 悄悄降级。

## 实际结果

第一份独立环境的统一检查：Ruff 通过，本地文件链接无缺失，默认测试 **339 passed in 3.64s**，课堂 7 项、HTTP 参考实现 29 项通过，pip check 无冲突。

第二份按精确清单安装的环境：全部 49 项版本匹配，Ruff 通过，默认测试 **339 passed in 3.44s**，课堂 **7 passed in 0.06s**，HTTP **29 passed in 0.08s**，pip check 无冲突。

独立源码副本中的真实本机演示：

- D4：201 成功、422 非法请求、504 模型预算到期；超时只保留 Analyst，最终报告为空。
- D5：AppTest 页面经真实本机 HTTP 进入 API 和异步内核；成功后展示 fake 标识，重跑不重发；下一次 Critic 失败保留部分结果并清除旧报告。
- 重启：同一个本机端口先后启动并关闭两个不同 PID 的 API 进程。相同 request_id 两次均完成三个阶段，但 review_id 不同；结果查询路径为 404。证据说明无持久化幂等或历史恢复，不能据此承诺重试只执行一次。

演示退出后均关闭本机监听和自有任务。没有真实模型请求、人工浏览器视觉验收或 TCP 断连取消保证。

## 随本轮完成的小型重构

请求标识规则移入纯契约模块，HTTP DTO 不再为了校验标识而导入 Service。URL 和时间配置由 UI 与服务共用校验；拒绝 URL 中的凭据、错误端口、查询与片段，避免把不适合 API 根地址的值推迟到网络层失败。超大整数预算统一为配置错误。

增加本地文档链接检查并纳入统一入口，保持教程、练习、当前说明与验收记录可跳转。CI 安装改为使用精确版本清单；远程 CI 仍未运行，最新完整状态见 [实施总览](../../technical/工程状态.md)。
