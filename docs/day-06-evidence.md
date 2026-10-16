# D6 实施记录：自动检查与事件日志

> 历史验收快照：正文的“当前”“下一步”、测试数量与接口描述以本阶段记录时为准。后续变更及现行状态见 [实施总览](implementation-status.md)，运行现有系统请按 [根 README](../README.md)。原命令含教学版本时，不直接覆盖现有源码。

日期：2026-10-16，Asia/Shanghai。依据第一周 D6 规划。本地自动检查与日志验收完成；GitHub Actions 配置已准备，**远程运行尚未执行**。没有提交或推送当前工作区，不将本地通过写成远程 CI 通过。

## 统一检查

```bash
.venv/bin/python -m pip install -e '.[test,dev]'
.venv/bin/python scripts/check.py
```

入口依次执行 Ruff、默认回归、课堂回归、HTTP 练习参考实现、pip check；失败立即以非零退出。Ruff 0.17.1，检查 Python 3.12 的导入、未使用符号和基础错误；修正导入顺序，保留 workflow 对 MAX_INPUT_CHARS 的显式兼容导出。未将刻意留 TODO 的练习实现纳入默认通过标准。

本轮实际结果：

- Ruff：All checks passed。
- 默认回归：332 passed in 3.94s。
- 课堂回归：7 passed in 0.07s。
- HTTP 参考实现：29 passed in 0.07s。
- pip check：No broken requirements found。

`.github/workflows/checks.yml` 为 Python 3.12 配置只读仓库权限、15 分钟期限、相同检查入口及 fake 本机 HTTP/UI 演示。无模型凭据或真实调用；未引入数据库、Docker、发布或部署步骤。

配置参考 [GitHub Python CI 文档](https://docs.github.com/en/actions/tutorials/build-and-test-code/python)、[setup-python](https://github.com/actions/setup-python) 与 [Ruff 配置](https://docs.astral.sh/ruff/configuration/)。使用查询时官方文档中的 checkout/setup-python v7；远程 runner 兼容性仍待实际 CI 验证。

## 日志

服务启动配置专用的 `review_system.events` logger，不修改根 logger。每行 JSON 仅包含：

```json
{"review_id":"00000000-0000-4000-8000-000000000001","stage":"Critic","status":"failed","elapsed_ms":21,"error_code":"model_timeout"}
```

上面是格式样例，不是真实故障记录。审核级事件 stage=null；阶段记录 running、succeeded、failed、cancelled 或 skipped。准入拒绝没有 review_id，错误码区分重复、满载、关闭。耗时使用单调时钟，审核耗时包含被接纳后的调度等待。

记录字段采用允许列表，不包含原文、提示词、模型回答、Key、request_id、异常文本或堆栈。未知错误码归为 internal_error，非法标识清空；测试覆盖嵌入私有文本、异常字段类型、非有限/过大耗时。日志接收器异常不能改变审核结果。

测试验证单次成功的 8 条事件顺序和同一 review_id，失败保留阶段与 skipped，取消与拒绝不同。配置重复执行不叠加专用 handler。日志不提供持久化报告或恢复能力，也不改变供应商或 Web 服务器自身的日志配置。

## 待完成

- 当前远程地址已配置，但本轮未向远程推送工作区，CI 真实运行待后续交付。
- live 验收继续受本机未配置模型凭据限制。
- 下一项 D7：固定依赖、在独立源码副本和干净虚拟环境复现检查与本机演示，并记录重启后的行为。
