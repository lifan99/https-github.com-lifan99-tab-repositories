# HTTP 前置知识：读懂 OpenAICompatibleClient

> 教学范围（2026-10-16 修订）：正文、题目和参考答案中的“客户端”“当前调用”均指保留的同步 OpenAICompatibleClient 与 urllib 练习，不代表应用主路径。当前页面通过本地 API，服务使用 AsyncOpenAICompatibleClient。完整调用链见 [首日材料](第一日阅读材料.md)，异步与预算见 [第三日材料](第三日阅读材料.md)。

编写日期：2026-10-16。建议用 25–35 分钟阅读，再打开 [clients.py](../review_system/clients.py) 对照。

本文面向已经能读 Python 函数、字典和异常，但还不熟悉网络请求的读者。学完应能解释：为什么要设置 URL、POST、请求头和请求体；为什么字典要转成字节；服务器返回什么；哪些失败要转换成 `LLMError`。

## 1. 客户端和服务端各做什么

当前系统有两段 HTTP：UI → 本地审核 API，以及后端 → 模型供应商。下图只展开第二段的通信概念；同步教学类与业务异步客户端不能混用。

HTTP 是客户端与服务端交换请求和响应的协议。本项目中，你的 Python 程序是客户端，模型提供商的接口是服务端。

```text
workflow.py：组织模型名和消息
    ↓ complete(model=..., messages=...)
clients.py：把参数装成 HTTP 请求
    ↓ 通过网络发送
模型提供商：处理请求、生成回答
    ↓ 返回 HTTP 响应
clients.py：读取 JSON、提取并检查回答
    ↓ 返回 str，失败时抛 LLMError
workflow.py：把回答交给下一角色
```

一次正常审核会依次发出三次模型请求。角色顺序由工作流决定；HTTP 客户端负责每一次通信。

HTTP 规定如何表达方法、状态、字段与内容；`model`、`messages` 和 `choices` 等字段属于具体模型接口的约定。HTTP 本身不要求请求体必须是 JSON。[HTTP 语义规范](https://www.rfc-editor.org/rfc/rfc9110.html#section-6)

## 2. URL：请求发到哪里

用一个仅供说明的地址拆解：

```text
https://example.invalid:443/v1/chat/completions
└协议┘ └────主机─────┘ 端口 └──────路径────────┘
```

| 部分 | 含义 | 对应到本项目 |
| --- | --- | --- |
| `https` | 通过 TLS 保护 HTTP 通信 | 由 `base_url` 配置 |
| `example.invalid` | 服务的主机名，示例域名不用于真实调用 | 实际运行换成提供商地址 |
| `443` | HTTPS 默认端口，通常可省略 | 也可由配置显式指定 |
| `/v1/chat/completions` | 服务内的目标路径 | 根地址加聊天接口路径 |

客户端拼接地址：

```python
f"{self.settings.base_url}/chat/completions"
```

如果 `base_url` 是 `https://example.invalid/v1`，最终地址就是 `https://example.invalid/v1/chat/completions`。配置里不要重复包含 `/chat/completions`；`Settings.from_env()` 会去掉根地址末尾的 `/`。

完整 URL 还可能有 `?name=value` 形式的查询参数和 `#section` 形式的片段。本项目的根地址校验拒绝这两种部分，模型输入放在请求体中。HTTPS 保护传输，但接收请求的提供商仍然能读取输入。[HTTP 与 HTTPS URI](https://www.rfc-editor.org/rfc/rfc9110.html#section-4.2)

## 3. 请求：方法、请求头、请求体

下面用 HTTP/1.1 的文本形式展示一次请求的主要部分。省略了库自动处理的长度等字段，也不表示需要手工拼接这段文本。

```http
POST /v1/chat/completions HTTP/1.1
Host: example.invalid
Content-Type: application/json
Authorization: Bearer synthetic-key

{"model":"fake-model","messages":[{"role":"user","content":"请审查"}],"stream":false}
```

第一行是方法、路径和协议版本；随后是请求头；空行后是请求体。

### 3.1 方法：希望服务端怎样处理

常见的 `GET` 用于获取资源的表示；`POST` 把内容交给目标资源按其约定处理。本项目的聊天接口约定使用 POST，所以代码显式写 `method="POST"`。不能仅凭“需要返回文字”就改成 GET。[GET 与 POST 的语义](https://www.rfc-editor.org/rfc/rfc9110.html#section-9.3)

POST 不代表正文一定是 JSON，也不代表一定要写数据库；正文格式和具体行为由接口约定。

### 3.2 请求头：怎样解释正文、怎样认证

| 请求头 | 本项目中的作用 | 容易混淆的地方 |
| --- | --- | --- |
| `Content-Type: application/json` | 声明当前请求正文是 JSON | 它不会替你把字典转换成 JSON |
| `Authorization: Bearer ...` | 携带访问凭证 | Bearer 是认证方案名，后面才是凭证 |
| `Host` | 标识目标主机 | 本项目交给 HTTP 库处理 |

请求头属于 HTTP 消息的元信息。请求体中的 `messages` 则是模型要阅读的数据。模型消息里的 `role="system"` 也是请求体字段，不是 HTTP 请求头。

设置请求的 `Content-Type`，不等于保证响应一定是 JSON；响应有自己的请求结果、响应头和正文。`Authorization` 用于认证，也不会自行加密凭证；传输保护依赖 HTTPS。[Content-Type](https://www.rfc-editor.org/rfc/rfc9110.html#section-8.3)、[Authorization](https://www.rfc-editor.org/rfc/rfc9110.html#section-11.6.2)

### 3.3 请求体：这次调用的具体数据

```python
{
    "model": model,        # 使用哪个模型
    "messages": messages,  # 模型阅读哪些消息
    "stream": False,      # 请求一次性返回结果
}
```

这些键属于当前聊天接口的约定。`stream=False` 让当前代码按完整 JSON 响应处理结果；如果改成流式返回，需要同时实现对应的流式读取和解析，不能只把布尔值改掉。

## 4. 为什么要把字典变成 JSON，再变成 bytes

Python 字典是程序内的数据结构，JSON 是可交换的文本格式，字节是这里发送请求正文的形式。

```text
dict / list
    ↓ json.dumps(...)
str：JSON 文本
    ↓ .encode("utf-8")
bytes：UTF-8 字节
    ↓ Request(data=...)，随后由 urlopen 发出
服务端接收并按接口约定解析
```

例如 Python 中写 `False`，序列化后 JSON 中是 `false`；Python 的 `None` 对应 JSON 的 `null`。JSON 字符串与键使用双引号，因此 `str(一个字典)` 不能代替 `json.dumps()`。

| 操作 | 输入 | 输出 |
| --- | --- | --- |
| `json.dumps(obj)` | Python 对象 | JSON 字符串 |
| `text.encode("utf-8")` | 字符串 | UTF-8 字节 |
| `json.loads(data)` | JSON 字符串或字节 | Python 对象 |
| `json.load(response)` | 提供 `read()` 的响应或文件对象 | Python 对象 |

`ensure_ascii=False` 控制中文是否直接出现在生成的 JSON 文本里，不是加密，也不负责 UTF-8 编码。当前客户端使用默认的 `json.dumps()`，中文可能显示为 `\uXXXX` 转义，服务端解析后仍能得到原文。[Python JSON 文档](https://docs.python.org/3.12/library/json.html)

本项目还把上下文字典编码成了 user 消息的 `content` 字符串，形成两层 JSON：外层满足聊天接口格式，内层组织原文与前序回答。可运行已有 [E03_json_request.py](two-hour-course/examples/E03_json_request.py) 观察两层分别解开后的内容。

## 5. 响应：状态码、响应头、响应体

一个简化的成功响应：

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"choices":[{"message":{"content":"这里是模型回答"}}]}
```

| 部分 | 回答的问题 | 本项目怎样使用 |
| --- | --- | --- |
| 状态码 `200` | 这次 HTTP 请求的结果类别是什么 | HTTP 库处理状态；错误进入异常分支 |
| 响应头 | 正文格式等元信息是什么 | 当前客户端直接尝试解析 JSON |
| 响应体 | 服务具体返回了什么 | `json.load(response)` 读取并解析 |

解析 JSON 后，`payload` 是 Python 对象，接着执行：

```python
content = payload["choices"][0]["message"]["content"]
```

依次取 `choices` 列表、第一项、`message` 字典、`content` 字段，再检查它是否为非空白字符串。

**HTTP 成功、JSON 能解析、响应字段正确、回答有用，是不同层次的判断。** 即使返回 `200`，正文也可能是 `{}`，触发字段缺失；即使得到非空回答，也不代表审核结论正确。

## 6. 常见状态码和没有状态码的失败

先记住分类：2xx 表示成功；3xx 与进一步操作或重定向有关；4xx 表示请求相关错误；5xx 表示服务端处理错误。以下是排查方向，具体原因仍以提供商说明为准。

| 状态码 | 基本含义 | 本项目中优先检查 |
| --- | --- | --- |
| `200` | 请求成功 | 继续解析并校验回答 |
| `400` | 请求有误 | 参数、请求结构是否符合接口约定 |
| `401` | 缺少有效认证凭证 | API Key、认证方式 |
| `403` | 服务拒绝执行 | 账号或资源权限 |
| `404` | 找不到目标资源，或服务不愿透露其存在 | 根地址与路径、资源标识 |
| `429` | 请求过多 | 速率限制；另核对提供商的额度说明 |
| `500` / `502` / `503` | 服务内部、网关或可用性问题 | 提供商状态及返回结果 |

状态码语义见 [HTTP 状态码规范](https://www.rfc-editor.org/rfc/rfc9110.html#section-15)；429 见 [RFC 6585](https://www.rfc-editor.org/rfc/rfc6585.html#section-4)。

连接失败、名称解析失败、TLS 握手失败或本地等待超时，可能发生在收到 HTTP 响应之前，因而没有可用的 HTTP 状态码。本地 `TimeoutError` 不等于服务端返回了 HTTP 408 或 504。

客户端把不同层次的已处理故障统一成 `LLMError`：

```text
收到 HTTP 错误状态          → HTTPError
连接失败或被包装的超时      → URLError
网络操作超时               → TimeoutError（也可能在 URLError.reason 中）
坏 JSON / 缺字段 / 空列表   → ValueError / KeyError / IndexError 等
读取故障或协议异常         → OSError / HTTPException 等
                           ↓
                       LLMError
```

这样工作流只需处理“模型调用失败”。HTTP 错误的公开消息保留状态码，不展示提供商错误正文；`raise ... from exc` 保留原始异常关联供调试。`HTTPError` 是 `URLError` 的子类，所以先捕获更具体的异常。[Python urllib 异常](https://docs.python.org/3.12/library/urllib.error.html)

## 7. 重定向、超时和同步等待

**重定向**是服务端要求客户端访问另一个位置，常见响应包含 3xx 状态和 `Location`。并非所有重定向状态都以相同方式处理 POST。

当前代码用 `add_unredirected_header("Authorization", ...)`，让认证头不自动复制到重定向请求；它不禁止全部重定向，也不检查配置地址是否可信。[Python 重定向请求头说明](https://docs.python.org/3.12/library/urllib.request.html#urllib.request.Request.add_unredirected_header)

**超时**由 `urlopen(request, timeout=...)` 设置，针对连接等网络阻塞操作，不能解释为整次请求的绝对总时限。即使配置 60 秒，也不能据此保证一次完整审核最多 180 秒。当前客户端没有自动重试。[Python urlopen 说明](https://docs.python.org/3.12/library/urllib.request.html#urllib.request.urlopen)

**同步等待**表示当前调用会等待网络结果，然后继续后面的语句。`Request(...)` 只构造请求对象；执行到 `urlopen(...)` 才发起网络操作。`with` 用于退出代码块时关闭响应资源，也适用于读取过程中发生异常的情况。

同步与流式是不同的概念：前者关心调用怎样等待，后者关心响应怎样交付。当前实现是同步调用，并请求非流式结果。

## 8. 把知识对应回源码

| 源码表达式 | HTTP / 数据概念 | 为什么这样写 |
| --- | --- | --- |
| `self.settings = settings` | 保存端点、凭证和等待配置 | 多次调用复用配置 |
| `base_url + "/chat/completions"` | 目标 URL | 定位聊天接口 |
| `method="POST"` | 请求方法 | 符合该接口的调用约定 |
| `headers={"Content-Type": "application/json"}` | 请求头 | 声明正文格式 |
| `json.dumps(...).encode("utf-8")` | 序列化与编码 | 把 Python 数据变成正文的字节 |
| `add_unredirected_header(...)` | 认证与重定向行为 | 限制凭证的自动转发 |
| `urlopen(request, timeout=...)` | 发起网络操作 | 发送并等待响应，设置阻塞操作超时 |
| `with ... as response` | 响应资源的生命周期 | 读取完成或失败后关闭资源 |
| `json.load(response)` | 读取、解析响应体 | 得到可按字段访问的 Python 对象 |
| `payload["choices"][0]["message"]["content"]` | 聊天响应结构 | 提取第一份回答 |
| `isinstance`、`strip()` | 返回值校验 | 保证成功返回非空白文本 |
| `except ...: raise LLMError(...)` | 对外的失败约定 | 上层不必理解所有网络异常 |

## 9. 离线练习：观察真实客户端怎样组装请求

在 `mvp` 目录执行下面的代码。地址和凭证都是合成值，`urlopen` 被替换为内存响应，不需要 `.env` 或网络连接。

```bash
.venv/bin/python - <<'PY'
from io import BytesIO
import json
from unittest.mock import patch

from review_system.clients import OpenAICompatibleClient
from review_system.config import Settings

settings = Settings(
    provider="qwen",
    base_url="https://example.invalid/v1",
    api_key="synthetic-key",
    model="fake-model",
    analyst_model="fake-model",
    critic_model="fake-model",
    judge_model="fake-model",
    timeout_seconds=12,
)
messages = [{"role": "user", "content": "请审查"}]
body = {"choices": [{"message": {"content": "模拟回答"}}]}
response = BytesIO(json.dumps(body, ensure_ascii=False).encode("utf-8"))

with patch("review_system.clients.urlopen", return_value=response) as send:
    answer = OpenAICompatibleClient(settings).complete(
        model="fake-model", messages=messages,
    )

request = send.call_args.args[0]
print("URL:", request.full_url)
print("方法:", request.get_method())
print("正文类型:", type(request.data).__name__)
print("正文内容:", json.loads(request.data))
print("超时配置:", send.call_args.kwargs["timeout"])
print("回答:", answer)
print("响应已关闭:", response.closed)
PY
```

应看到 POST、正文类型 `bytes`、包含 `model/messages/stream` 的字典、超时配置 12、回答“模拟回答”，以及响应已关闭 `True`。这证明了本地请求构造与响应提取，不验证真实服务连通性。

再分别把响应 `body` 改成 `{}`、`{"choices": []}` 和 `{"choices": [{"message": {"content": "   "}}]}`，预测会出现哪类 `LLMError`。已有 [test_clients.py](../tests/test_clients.py) 还覆盖 HTTP 错误、超时、断流和重定向凭证行为，可运行：

```bash
.venv/bin/python -m pytest -q tests/test_clients.py
```

## 10. 闭卷自测

1. `Content-Type` 会自动把字典转换成 JSON 吗？
2. `Request(...)` 和 `urlopen(...)` 哪一个真正发请求？
3. 返回 HTTP 200，是否足以保证 `complete()` 返回文本？
4. 本地超时是否一定对应 HTTP 504？
5. 为什么认证头用 `add_unredirected_header` 添加？
6. `stream=False` 是否意味着调用已经是异步的？

参考答案：1. 不会，正文靠 `json.dumps()` 序列化。2. `urlopen`。3. 不足，还要解析 JSON、提取字段、校验非空白文本。4. 不一定，可能根本没有收到响应。5. 避免自动复制认证头到重定向请求。6. 不是，它表达响应交付方式；当前调用仍同步等待。

下一步回到 [手写模型客户端](从零手撕多智能体审查项目.md#s10)，按“组请求 → 发请求 → 读响应 → 校验文本 → 转换异常”解释每一段代码。

需要进一步巩固时，完成 [HTTP 补充练习](HTTP补充练习.md)：12 题、100 分，含三道离线编程题和独立参考答案。

## 11. 从同步教学类对应到当前异步客户端

| 教学类写法 | 业务主路径写法 | 共同目标或差异 |
| --- | --- | --- |
| Request + urlopen | await http_client.post | 构造并发送 POST，异步主路径可让出控制权 |
| json.dumps + encode | post(json=...) | 外层 JSON 编码由 HTTPX 处理 |
| json.load(response) | response.json() | 解析供应商响应外壳，之后仍需业务校验 |
| add_unredirected_header | follow_redirects=False | 主路径直接拒绝重定向 |
| urllib timeout | HTTPX 操作超时 + 模型预算 + 总预算 | 预算不是三个网络超时简单相加 |
| with 关闭单个响应 | 外层 async with 管理共享 HTTP 客户端 | 单份审核不能关闭无关审核仍借用的客户端 |

对照 [test_async_clients.py](../tests/test_async_clients.py) 与第三日阅读材料。stream=False 在两类客户端中都表示非流式响应，与同步/异步相互独立。
