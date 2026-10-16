# HTTP 补充练习参考答案

> 教学范围（2026-10-16 修订）：正文、题目和参考答案中的“客户端”“当前调用”均指保留的同步 OpenAICompatibleClient 与 urllib 练习，不代表应用主路径。当前页面通过本地 API，服务使用 AsyncOpenAICompatibleClient。完整调用链见 [首日材料](第一日阅读材料.md)，异步与预算见 [第三日材料](第三日阅读材料.md)。

对应 [练习题](HTTP补充练习.md)。先独立作答，再核对理由。评分允许等价表述；编程题固定公开错误文字是为了与现有客户端对照，并方便验收。

## Q01：地址拆解

1. 协议 `https`；主机 `example.invalid`；端口 `8443`；根地址的路径 `/compatible-mode/v1`。
2. 最终 URL：`https://example.invalid:8443/compatible-mode/v1/chat/completions`。
3. 若根地址已含接口路径，会拼出重复的 `/chat/completions/chat/completions`。这与期望路径不一致，可能找不到资源；不能保证所有服务都返回同一种错误状态。

## Q02：请求结构

1. 方法 POST；路径 `/v1/chat/completions`；版本 HTTP/1.1。
2. `Host`、`Content-Type`、`Authorization` 是请求头，空行之后的 JSON 是正文。
3. `Content-Type` 声明正文格式；`Authorization` 携带认证凭证。
4. `role="system"` 位于 JSON 正文的 `messages` 中，它是模型消息的角色字段。
5. 三个键是该模型接口的字段约定，HTTP 不强制要求这些名字。

## Q03：五项均为错误

1. `Content-Type` 只做声明。本题采用 JSON 字节正文，需要显式序列化与编码。
2. POST 不限定正文必须是 JSON；格式由接口约定。
3. Bearer 是认证方案，不是加密算法。HTTPS 负责传输保护。
4. `stream=False` 选择响应交付方式；当前调用仍同步等待。
5. `Request` 是请求描述对象；执行发送函数才发起网络操作。

## Q04：类型与编码

1. 依次为 `dict`、`str`、`bytes`、`dict`。
2. JSON 中是小写 `false`，解析回 Python 后是 `False`。
3. `True`。
4. `str(body)` 产生 Python 的字典表示，通常有单引号和 `False`，不符合 JSON 语法。编码只能把文本变成字节，不能修复格式。
5. 不会。`\uXXXX` 是 JSON 的转义表示，解析后恢复对应字符。

## Q05：分类表

以下公开文字来自当前 [clients.py](../review_system/clients.py)。所有表内失败最终都抛出 `LLMError`。

| 场景 | 类别 | 公开文字 |
| --- | --- | --- |
| HTTP 401 | HTTP 错误状态 | `Provider request failed (HTTP 401).` |
| HTTP 429 | HTTP 错误状态 | `Provider request failed (HTTP 429).` |
| HTTP 503 | HTTP 错误状态 | `Provider request failed (HTTP 503).` |
| `URLError("unavailable")` | 传输/连接故障 | `Could not connect to the model provider.` |
| `TimeoutError()` | 传输/连接故障 | `Provider request timed out.` |
| 正文 `not json` | JSON 或字段结构错误 | `The provider returned an invalid chat response.` |
| 正文 `{}` | JSON 或字段结构错误 | 同上：缺少 `choices` |
| `choices` 为空列表 | JSON 或字段结构错误 | 同上：无法取第 0 项 |
| `content` 为 `null` | 回答内容错误 | `The provider returned empty or non-text content.` |
| `content` 为纯空格 | 回答内容错误 | 同上：去掉空白后没有内容 |

状态码的基本含义可核对 [HTTP 状态码规范](https://www.rfc-editor.org/rfc/rfc9110.html#section-15)。这里的错误文字是项目的设计选择。

## Q06：修复示例

```python
request = Request(
    base_url + "/chat/completions",
    data=json.dumps(body).encode("utf-8"),
    headers={"Content-Type": "application/json"},
    method="POST",
)
request.add_unredirected_header("Authorization", "Bearer synthetic-key")
```

四处分别是：Python 字典表示换成 JSON；正文类型声明改为 JSON；GET 改为 POST；认证头使用不会自动复制到重定向请求的方式添加。

POST 不会自动把正文转成 JSON。方法、正文的实际内容、格式声明必须分别正确。

## Q07：请求构造

完整代码见 [solution.py](http-practice/solution.py) 的 `build_request()`。

先处理末尾 `/`，再拼接口路径；用传入的模型和消息构造字典，序列化并编码为字节；声明格式和 POST 方法；最后附加不可自动转发的认证头。

本题比当前客户端多兼容一次根地址末尾 `/`。当前项目在 `Settings.from_env()` 中做这一步，因此应用客户端直接使用配置值。

判分关注生成的请求行为，不限定字典键顺序或是否直接保留中文。不要通过把 `messages` 改成字符串来凑出一份看起来像 JSON 的正文。

## Q08：响应提取

完整代码见 `solution.py` 的 `parse_response()`。

将读取、JSON 解析和取字段放在结构异常的处理范围内；拿到 `content` 后，再独立检查类型和非空白。最后返回原始 `content`。

为什么不直接 `return content.strip()`？因为它会改写原始回答。这里的 `strip()` 只是合法性检查。

为什么不在这里关闭响应？因为这个函数借用传入的可读对象，外层完整调用负责生命周期。拆分后要明确资源由谁拥有。

本题不把 `IncompleteRead` 这种读取故障改成“JSON 格式错误”；它应交由 Q09 的传输异常处理。

## Q09：完整调用

完整代码见 `solution.py` 的 `complete_with_transport()`。

它将组装请求、发送、解析串起来，同时用 `with` 关闭响应。具体的发送能力由 `send` 注入，所以同一段代码可以被离线验收。

捕获顺序要考虑继承关系：`HTTPError` 继承 `URLError`，后者继承 `OSError`；`TimeoutError` 也属于 `OSError`。先处理具体情形，最后处理宽泛情形。[Python urllib 异常说明](https://docs.python.org/3.12/library/urllib.error.html)

公开消息使用受控文字，`from exc` 保留调试关联。这个约定只限制公开字符串，不承诺原始异常堆栈也完全不含底层信息。

不要把失败变成 `return ""`，也不要捕获 `BaseException`。`KeyboardInterrupt` 应继续传播，让使用者能中断工作。

检查参考实现：

```bash
HTTP_PRACTICE_IMPL=solution .venv/bin/python -m pytest -q docs/http-practice/test_exercises.py
```

这条命令检查答案文件，不表示你的 `exercise.py` 已通过。自测要显式选择 `HTTP_PRACTICE_IMPL=exercise`。

## Q10：重定向

1. 在题目指定的标准库 302 本地重定向构造中，普通 `add_header` 添加的 Authorization 会被复制；`add_unredirected_header` 添加的不会。
2. 后续地址可能不同，自动转发会扩大凭证的接收范围。
3. 不会禁止所有重定向，也不会证明初始配置地址可信。
4. 不能。离线检查只证明请求头复制行为，不覆盖真实服务器、TLS、网络或提供商的重定向策略。

这是题目指定的 urllib 行为，不能直接推导所有 HTTP 库都如此。[Python 请求头与重定向说明](https://docs.python.org/3.12/library/urllib.request.html#urllib.request.Request.add_unredirected_header)

## Q11：超时与重试

三处问题：

- `urlopen` 的 timeout 面向网络阻塞操作，不等于每阶段的绝对总时限，不能直接乘三得出整轮上限。
- 本地超时不代表收到了 HTTP 504，也可能还没收到任何 HTTP 响应。
- 超时可能发生在服务已经接受请求之后。再次调用可能产生重复执行或费用；是否重试需要结合失败原因、服务约定和剩余预算决定。当前客户端没有自动重试。

如果要做整轮 36 秒期限，应定义统一开始时间与截止时间；把剩余预算传给阶段调用，并明确超时后如何停止或取消工作、关闭资源、保留已完成结果。调用方停止等待，也不能直接保证远端计算已停止。这里是设计要求，不是本练习已实现的能力。

timeout 的具体语义见 [Python urlopen 文档](https://docs.python.org/3.12/library/urllib.request.html#urllib.request.urlopen)。

## Q12：口述参考

可以用自己的话表达以下五点：

1. 客户端把模型名和消息放进 JSON 正文，目标是根地址加 `/chat/completions`，使用 POST、JSON 格式头与 Bearer 认证头。
2. 字典是 Python 对象，JSON 是交换文本，UTF-8 编码产生当前请求使用的字节正文。
3. 发送后读取响应、解析 JSON、取第一份消息内容、验证非空白文本，最终返回原文；失败则抛异常。
4. HTTP 200 只说明 HTTP 层的请求结果，仍可能解析或校验失败；非空白字符串也不能证明模型结论正确。
5. 客户端统一通信故障，工作流就能专注角色顺序、上下文和部分结果恢复，并替换不同客户端实现。

复盘时记录三项：错在哪里、对应源码或知识点是什么、下次用什么输入验证。完成后返回 [练习题](HTTP补充练习.md)。
