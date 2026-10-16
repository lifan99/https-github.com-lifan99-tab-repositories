# HTTP 补充练习：从请求结构到模型客户端

> 教学范围（2026-10-16 修订）：正文、题目和参考答案中的“客户端”“当前调用”均指保留的同步 OpenAICompatibleClient 与 urllib 练习，不代表应用主路径。当前页面通过本地 API，服务使用 AsyncOpenAICompatibleClient。完整调用链见 [首日材料](第一日阅读材料.md)，异步与预算见 [第三日材料](第三日阅读材料.md)。

编写日期：2026-10-16。共 12 题、100 分，建议用 90–120 分钟完成。前置材料：[HTTP 前置知识](HTTP前置知识：读懂模型客户端.md)。

目标：能独立构造一次模型 HTTP 请求，读懂响应，分清 HTTP 状态、传输故障和内容校验，并解释 `OpenAICompatibleClient` 为什么这样写。

## 使用方法

先做 Q01–Q06，再完成 Q07–Q09 的代码，最后做 Q10–Q12。判断题和排错题都要写理由，不能只记结论。答案单独放在 [参考答案](HTTP补充练习参考答案.md)，建议完成一轮再打开。

| 阶段 | 题目 | 分值 | 建议时间 |
| --- | --- | --- | --- |
| 识别与推演 | Q01–Q06 | 35 | 25–30 分钟 |
| 编程 | Q07–Q09 | 45 | 45–65 分钟 |
| 排查与解释 | Q10–Q12 | 20 | 20–25 分钟 |

编程文件：

| 文件 | 用途 |
| --- | --- |
| [exercise.py](http-practice/exercise.py) | 作答文件，含三个 TODO |
| [test_exercises.py](http-practice/test_exercises.py) | 离线验收，按题号选择运行 |
| [solution.py](http-practice/solution.py) | 参考实现，先保留不看 |

在 `mvp` 项目根目录执行以下命令。练习使用合成配置、内存响应和注入的发送函数，不需要 `.env`、API Key 或外部服务。测试会阻止网络连接。

```bash
cd /home/fanli/ai-engineering/multi-agent/mvp

# 每完成一道编程题，检查这一题。
HTTP_PRACTICE_IMPL=exercise .venv/bin/python -m pytest -q docs/http-practice/test_exercises.py -k q07
HTTP_PRACTICE_IMPL=exercise .venv/bin/python -m pytest -q docs/http-practice/test_exercises.py -k q08
HTTP_PRACTICE_IMPL=exercise .venv/bin/python -m pytest -q docs/http-practice/test_exercises.py -k q09

# 三题完成后，检查全部编程题。
HTTP_PRACTICE_IMPL=exercise .venv/bin/python -m pytest -q docs/http-practice/test_exercises.py
```

初始骨架抛出 `NotImplementedError` 是预期现象，表示尚未作答。默认项目测试只收集 `tests/`，不会运行这些未完成的教学题。

## Q01：拆解目标地址（5 分）

给定：

```text
base_url = https://example.invalid:8443/compatible-mode/v1
```

1. 写出协议、主机、显式端口、根地址中的路径。（2 分）
2. 按本项目约定写出最终聊天接口的完整 URL。（1 分）
3. 如果把 `base_url` 配成已经含有 `/chat/completions` 的完整接口地址，当前客户端会拼出什么？为什么可能失败？（2 分）

## Q02：标注一份请求（5 分）

这是一份简化示意，省略自动生成的部分字段：

```http
POST /v1/chat/completions HTTP/1.1
Host: example.invalid
Content-Type: application/json
Authorization: Bearer synthetic-key

{"model":"fake-a","messages":[{"role":"system","content":"你是审查员"}],"stream":false}
```

1. 标出请求方法、目标路径和协议版本。（1 分）
2. 列出请求头和请求体的边界。（1 分）
3. `Content-Type` 和 `Authorization` 各负责什么？（1 分）
4. `role="system"` 属于请求头还是请求体？（1 分）
5. `model/messages/stream` 是 HTTP 强制规定的字段吗？（1 分）

## Q03：判断并解释（5 分）

每题 1 分，判断和理由都正确才得分。

1. 只要设置 `Content-Type: application/json`，就可以把 Python 字典原样放进这里的 `Request(data=...)`。
2. POST 的正文必须是 JSON。
3. `Authorization: Bearer ...` 会自动把 API Key 加密。
4. 设置 `stream=False` 后，这个网络调用就成为异步调用。
5. `Request(...)` 构造成功，说明服务端已经收到请求。

## Q04：追踪字典、字符串和字节（5 分）

先预测，再在 Python 中验证：

```python
import json

body = {"content": "中文", "stream": False}
text = json.dumps(body, ensure_ascii=False)
data = text.encode("utf-8")
restored = json.loads(data)
```

1. 分别写出 `body/text/data/restored` 的类型。（1 分）
2. `text` 中的布尔值拼写是什么？（1 分）
3. `restored == body` 的结果是什么？（1 分）
4. `str(body).encode("utf-8")` 为什么不能可靠地替代前两次转换？（1 分）
5. 默认 `json.dumps(body)` 中中文显示成 `\uXXXX`，解析后是否丢失中文？（1 分）

## Q05：对失败进行分层（10 分）

按四类填写下表：**HTTP 错误状态、传输/连接故障、JSON 或字段结构错误、回答内容错误**。再写出当前客户端的处理结果。每行 1 分，类别与处理都正确才得分。

| 场景 | 类别 | 处理结果 |
| --- | --- | --- |
| 服务返回 HTTP 401 | 待填 | 待填 |
| 服务返回 HTTP 429 | 待填 | 待填 |
| 服务返回 HTTP 503 | 待填 | 待填 |
| 发起连接时抛出 `URLError("unavailable")` | 待填 | 待填 |
| 网络操作抛出 `TimeoutError()` | 待填 | 待填 |
| HTTP 200，正文是 `not json` | 待填 | 待填 |
| HTTP 200，正文是 `{}` | 待填 | 待填 |
| HTTP 200，正文是 `{"choices": []}` | 待填 | 待填 |
| HTTP 200，`content` 是 `null` | 待填 | 待填 |
| HTTP 200，`content` 是三个空格 | 待填 | 待填 |

## Q06：修复一段请求构造代码（5 分）

已知接口要求 POST、JSON 正文，并使用本项目的认证头策略：

```python
body = {"model": "fake", "messages": messages, "stream": False}
request = Request(
    base_url + "/chat/completions",
    data=str(body).encode("utf-8"),
    headers={"Content-Type": "text/plain"},
    method="GET",
)
request.add_header("Authorization", "Bearer synthetic-key")
```

指出并修复四处与约定不一致的地方，每处 1 分。再说明“修正为 POST”是否会自动解决正文格式问题，1 分。

## Q07：手写请求构造（15 分）

完成 `exercise.py` 的 `build_request()`。输入的根地址已经过配置层校验；本题不要求重新实现 URL 验证。

验收要求：

- 正确保留根地址的已有路径，兼容有或没有末尾 `/` 的输入。（3 分）
- 方法为 POST，正文为 JSON 的 UTF-8 字节，`Content-Type` 正确。（4 分）
- 使用传入的 `model/messages`，`stream` 为 `False`，不改写消息列表。（4 分）
- 用 `add_unredirected_header` 附加 Bearer 凭证，不执行发送操作。（4 分）

提示：可以使用 `json.dumps()`、`encode()` 和 `Request`。`ensure_ascii` 两种设置均可，只要中文往返后保持不变。

## Q08：手写响应提取（15 分）

完成 `parse_response(response)`。参数是可以读取的响应对象，本题不接收 URL，不发送请求。

验收要求：

- 从 JSON 响应中提取第一项 `choices[0].message.content`。（4 分）
- 返回非空白字符串；校验时使用 `strip()`，返回时保留原始文本。（3 分）
- JSON 或结构异常转换成 `LLMError("The provider returned an invalid chat response.")`，保留异常链。（4 分）
- 非字符串或纯空白回答抛出 `LLMError("The provider returned empty or non-text content.")`。（2 分）
- 本函数不关闭调用方传入的资源。（2 分）

提示：在这一步区分“字段拿不到”和“字段拿到了但内容不合格”。让读取时的网络故障继续抛出，由下一题处理。

## Q09：组合成一次完整调用（15 分）

完成 `complete_with_transport()`，复用 Q07、Q08。`send` 是必填的函数参数，作用相当于传入一个可替换的 `urlopen`，调用形式为：

```python
with send(request, timeout=settings.timeout_seconds) as response:
    ...
```

测试会传入 `Mock(return_value=BytesIO(...))` 模拟成功，或用 `Mock(side_effect=某个异常)` 模拟失败。

验收要求：

- 使用传入模型和消息构造请求，调用 `send` 一次，传入配置超时。（3 分）
- 通过上下文管理器使用响应，成功、解析失败、读取中断时都退出上下文。（3 分）
- 按下表转换网络异常，使用 `raise ... from exc`，保留 Q08 的 `LLMError`。（6 分）
- 不重试、不返回空字符串冒充成功、不读取真实配置；`KeyboardInterrupt` 继续传播。（3 分）

| 底层情况 | `LLMError` 的公开文字 |
| --- | --- |
| `HTTPError` | `Provider request failed (HTTP 状态码).`，例如 `Provider request failed (HTTP 401).` |
| `TimeoutError`，或 `URLError.reason` 是 `TimeoutError` | `Provider request timed out.` |
| 其他 `URLError` | `Could not connect to the model provider.` |
| 其他 `OSError` | `Provider connection failed while reading the response.` |
| `HTTPException` | `Provider connection was interrupted.` |

公开文字不包含底层异常中的 `synthetic-private` 合成内容。不要用 `except BaseException` 捕获所有退出信号。

## Q10：重定向后凭证去哪了（5 分）

构造两个相同请求，唯一差别是：

```python
request_a.add_header("Authorization", "Bearer synthetic-key")
request_b.add_unredirected_header("Authorization", "Bearer synthetic-key")
```

1. 用 `HTTPRedirectHandler().redirect_request(...)` 本地构造一个 302 重定向请求时，哪个凭证会被复制？（2 分）
2. 为什么这个差别值得专门测试？（1 分）
3. B 的写法是否禁止了一切重定向，或保证初始端点可信？（1 分）
4. 构造重定向对象的离线检查，能否证明真实提供商的重定向链可用？（1 分）

可阅读验收文件中的 `test_q07_redirect_credentials`，这里不会访问目标地址。只讨论题目指定的标准库行为。

## Q11：检查超时承诺（5 分）

有人说：“配置 `timeout_seconds=12`，所以三个角色合计一定在 36 秒内结束；超时就说明服务器返回了 504。既然失败了，直接再请求一次就行。”

指出三处不能直接成立的推论，3 分。再说明如果产品真的要求“整轮 36 秒内结束”，还需要定义什么，2 分。只写设计，不要求实现异步或整轮期限。

## Q12：最终口述（10 分）

不看源码，用自己的话解释下面的完整路径，每项 2 分；每项的结论与理由各 1 分：

1. 从 `complete(model=..., messages=...)` 到目标 URL、请求头和请求体，各包含什么？
2. Python 数据为什么要经历 JSON 序列化和 UTF-8 编码？
3. 响应如何变成一个可供工作流使用的字符串？
4. 收到 HTTP 200、得到可用字符串、得到正确审核结论，三者有什么区别？
5. 为什么由客户端统一抛 `LLMError`，而不要求工作流捕获每一种网络异常？

## 完成与复盘

自动检查覆盖编程契约，笔答部分按参考答案自行评分。测试通过不能替代口述解释。

- 85–100 分：再脱离骨架写一次完整调用，并对照当前客户端。
- 65–84 分：按失分点复习请求/响应边界、序列化或异常处理，重做对应题。
- 低于 65 分：先重做 Q01–Q06，再逐题运行 Q07、Q08、Q09 的检查。

参考答案与解释：[HTTP 补充练习参考答案](HTTP补充练习参考答案.md)。
