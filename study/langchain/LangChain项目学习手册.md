# 从现有项目学 LangChain

适合当前基础的分步技术手册

## 这份文档怎样适配你的学习方式

你的项目记录已确认完成字典、函数、三角色顺序和普通失败的入门阶段，正在开始对照真实工作流，观察 Critic 收到的材料。本手册从这个位置接入 LangChain，把新接口逐个对应到已经见过的数据和动作。

学习主线只有一条：字典进入一个步骤，步骤返回结果，结果由程序明确保存，再交给下一步。先沿着这条线理解组件，再逐渐接触真实模型、Agent 和检索。

本文使用规范拼写 LangChain。入门部分主要使用它的 `langchain-core` 组件；官方完整 Agent 入口另有 `create_agent`，放在后续路线中认识。本手册没有把当前项目改造成框架应用。

学习安排采用你现有路线中的方法：先预测，再观察，只改一处，最后用自己的话解释。每个任务只增加一个主要概念。示例使用固定回答，因此观察重点是请求、返回类型和数据传递。

手机阅读时，可以只看正文、代码和预期现象，先写下自己的判断。电脑操作放在每节后半部分，方便有时间时验证。一次建议只完成一个任务；核心路径六个任务，可各安排约十五至二十五分钟，实际用时按理解情况调整。

后面还有项目对照、失败解释、术语和后续路线，用于按需查阅。阅读过、运行过、能够解释，分别是不同证据，不自动记为个人学习阶段完成。

示例依据 2026 年 10 月 19 日可见的 LangChain 官方文档和公开源码编写。项目主环境当前没有安装 LangChain。本文配有独立脚本与安装说明，核验范围在文末列明。

## 先建立一张学习地图

前置确认：普通 Python 如何把初审保存到上下文。对应脚本 E00，不需要新依赖。如果这一步能解释，就直接进入任务一。

任务一：把普通函数包装成一个可调用步骤，认识 `RunnableLambda` 与 `invoke`。只观察函数被怎样调用，不接入模型。

任务二：把材料字典变成消息，认识 `ChatPromptTemplate`。只观察模板需要哪些键、生成哪些文字，不要求模型回答。

任务三：让固定模型返回一条消息，认识 `FakeListChatModel` 和 `AIMessage`。只区分消息对象与回答正文。

任务四：把模板、模型、文本输出组合起来，认识 `|`。先分别调用，再观察链式调用是否得到相同文本。

任务五：显式保存初审，再交给 Critic。把框架例子对应到你当前正在观察的真实项目问题。

任务六：增加 Judge，完成一份独立的三角色教学流程。只验证角色顺序、材料增加和固定输出，不把它当成完整业务工作流。

这张地图是依赖顺序，不是每日计划。卡在某一项时，先处理该项的输入、返回类型或具体报错，不追加新的框架功能。当前项目中的阶段五任务仍以原有记录为准。

## 阅读前先分清几个名称

LangChain 是用于构建模型应用和 Agent 的框架体系。当前官方概览强调模型、工具和 Agent 运行结构；本手册先使用核心组件，理解其中可组合的输入输出约定。[官方概览](https://docs.langchain.com/oss/python/langchain/overview)

`langchain-core` 是本册使用的 Python 包，导入名写成 `langchain_core`。包名里的连字符和导入名里的下划线不同，这是正常的命名方式。

LangGraph 提供更底层的流程编排能力。LangSmith 用于运行追踪与评估。它们和 LangChain 有联系，但完成本册的固定回答练习，不需要先学习图编排或配置追踪账号。

模型提供商的集成通常使用相应适配包。核心练习先不选择供应商，因此没有 API Key、模型权限或费用这一层干扰。等数据传递能够解释以后，再学习真实模型配置更容易定位问题。

本项目原本已经有自己的客户端协议、工作流和报告契约。学习这些组件的目的，是理解可复用的接口，并判断以后哪些地方确实值得采用。框架不会自动保留原有业务保证。

## 前置确认　普通 Python 怎样交接材料

先看你已经熟悉的三行。这里省略函数定义，只表达执行顺序：

```python
context = {"original_input": "历史只在本次运行期间保留。"}
context["analyst_output"] = analyst(context)
result = critic(context)
```

第一行建立原文。第二行先调用初审函数，再把返回值保存到 `analyst_output`。第三行调用 Critic 时，字典里已经同时有原文和初审。

这段代码中，角色之间没有自动共享记忆。Critic 能读取初审，是因为程序先保存，再传入同一份上下文。后面换成 LangChain，这项责任依然存在。

`analyst(context)` 得到的字符串，与 `context` 字典是不同对象。把字符串赋给变量不会自动增加字典字段；必须执行对应赋值，后续代码才能按键取得它。

完整脚本 [E00_plain_context.py](examples/E00_plain_context.py) 包含初审和质疑两个普通函数。初审永远返回固定说明，Critic 拼接原文与初审用于观察，没有调用模型。

先预测：只把原文改成另一句话，哪一行输出会变，初审会不会自动重新评价？再看预期：原文部分变化，固定初审不变。这个差异来自函数定义，不表示材料没有传入。

如果在电脑操作，在终端运行：

```bash
python3 /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/examples/E00_plain_context.py
```

能指出初审保存位置，并解释 Critic 为什么能拿到它，就足够进入任务一。若仍然把终端输出当成函数返回值，先回看项目原有的函数练习，不急于增加框架接口。

## 任务一　从函数调用认识 invoke

本节只理解一件事：一个普通函数可以包装成 LangChain 的可调用步骤，再通过统一入口调用它。

普通 Python 写法是 `read_original(context)`。下面先定义同样的函数，再包装它：

```python
from langchain_core.runnables import RunnableLambda

def read_original(context):
    return context["original_input"]

step = RunnableLambda(read_original)
```

`RunnableLambda` 接收的是函数对象 `read_original`。这里没有在函数名后加括号，因为我们要把“以后怎样处理输入”交给组件，而不是马上执行一次函数。

`step` 代表一个可运行步骤。创建它时，还没有从某份材料里取出原文。传入具体字典并执行，要到 `step.invoke(context)` 才发生。

在这份例子中，可以这样比较：

```python
context = {"original_input": "历史只在本次运行期间保留。"}
direct = read_original(context)
wrapped = step.invoke(context)
```

两个变量得到相同字符串。`invoke` 不会自动添加智能能力，也不会替函数补全字段。包装后的步骤仍然执行原函数的逻辑。

### 先预测，再核对

预测三个事实：输入是字典还是字符串；返回值是字典还是字符串；原始字典有没有增加新键。可以先不看后面的解释。

核对：本例输入是字典，返回值是原文字符串，字典没有增加新键。函数只读取 `original_input`，没有修改上下文。返回值类型由这个函数决定，不由 `invoke` 统一变成某一种形式。

如果字典里没有 `original_input`，函数按键读取会抛出错误。包装成 Runnable 以后，这个数据前提仍然存在。框架接口没有消除函数自己的输入要求。

完整脚本 [E01_runnable.py](examples/E01_runnable.py) 会分别打印直接调用、包装调用和返回类型。电脑运行前，先按附录准备独立学习环境。

### 只改一处

在自己的练习副本里，只改变 `original_input` 对应的文字。预测两个返回结果是否一起改变，再运行核对。不要同时修改函数、输入键名和打印位置，否则很难判断变化来自哪里。

最后尝试解释：`RunnableLambda(read_original)` 做了什么，`step.invoke(context)` 又做了什么。能分清创建步骤与执行步骤，本节就达到目的。

与项目的联系：现在的工作流已经调用客户端与校验函数。Runnable 提供的是一种统一的调用和组合方式，业务函数接收什么、交出什么，仍然要明确设计。

接口依据：[RunnableLambda 官方参考](https://reference.langchain.com/python/langchain-core/runnables/base/RunnableLambda)。

## 任务二　把 Critic 的材料变成消息

本节只理解：提示词模板怎样从字典取值，生成模型将要阅读的消息。准备消息本身不调用模型。

先看模板定义：

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages([
    ("system", "你是 Critic，核对原文和初审。"),
    ("human", "原文：{original_input}\n初审：{analyst_output}"),
])
```

第一条消息说明职责，第二条消息放待评价材料。`{original_input}` 与 `{analyst_output}` 是模板变量，名字要与传入字典的键对应。

这与项目当前的 system 消息和 user 材料消息在用途上相近。这里使用核心组件的消息表示，项目原代码使用角色字典与 JSON 上下文；表示不同，仍需要明确材料来源。

准备字典后执行：

```python
context = {
    "original_input": "历史只在本次运行期间保留。",
    "analyst_output": "[固定初审] 请说明历史保留范围。",
}
value = prompt.invoke(context)
messages = value.to_messages()
```

此处 `value` 是提示词值对象。`.to_messages()` 把它转成消息列表。列表中的消息对象保存类别与正文，可以用 `message.type` 和 `message.content` 查看。

### 先预测，再核对

预测生成几条消息，哪条包含原文和初审，以及这时有没有 Critic 回答。核对：共两条，材料进入第二条 human 消息；此时只准备好了请求，没有模型回答。

完整脚本 [E02_prompt.py](examples/E02_prompt.py) 先打印模板变量，再逐项打印消息。应关注正文里的值是否来自你传入的两个字段，不需要记住整个对象的调试表示。

如果把模板变量写成 `{analysis}`，却只传 `analyst_output`，会缺少所需变量。应该核对模板和字典，而不是先改供应商地址。此时尚未发生网络请求。

字典中多保存一个字段，也不代表模板一定会使用它。模型能读到什么，以生成的消息为准；观察 `context` 与观察最终消息是两个连续步骤。

### 只改一处

先只改初审的文字，预测哪条消息的哪一部分改变；确认以后，再在另一轮练习只改原文。不要同时改两项，以便保留对照依据。

最后用自己的话说明：模板中的花括号对应哪个键，谁把值放进去，为什么准备完消息仍然没有模型回答。这与当前项目“看清 Critic 收到什么”的目标直接相连。

接口依据：[ChatPromptTemplate 官方参考](https://reference.langchain.com/python/langchain-core/prompts/chat/ChatPromptTemplate)。

## 任务三　模型返回的是一条消息

本节只理解：聊天模型调用的返回值，可以是带正文的消息对象。先把“对象”和“对象里的文字”分开，再去看后面的解析器。

核心示例使用固定模型：

```python
from langchain_core.language_models.fake_chat_models import FakeListChatModel

model = FakeListChatModel(
    responses=["[fake] 固定初审回答。"]
)
answer = model.invoke(value)
```

这里的 `value` 是上一节由模板准备的提示词值。完整脚本会重新创建模板，所以运行文件时不依赖你先在另一个文件中建立变量。

本例 `answer` 是 `AIMessage`，正文通过 `answer.content` 读取。`print(answer)` 可能包含额外对象信息；只需要看回答文字时，打印正文更明确。

这与前两节再次形成区别：普通函数步骤返回字符串，模板步骤返回提示词值，聊天模型返回消息对象。它们都可以使用 `invoke`，返回值却不必相同。

### 固定模型到底做什么

`FakeListChatModel` 依据预设列表返回文字，适合观察接口与数据流。它不会分析你输入的方案，也不会因为改了 system 提示词就自行形成不同意见。

本册每个固定模型主要只设置一份回答。完整脚本每次启动重新创建对象，便于重复观察。以后使用多份预设回答时，还要理解调用次数与内部顺序，不能把变化误认为真实推理。

因此，改原文后回答仍然相同，是这个示例预期的性质。判断原文是否传对，应该看准备的消息；判断接口是否返回文本，则看本节的消息对象和正文。

### 先预测，再核对

预测 `type(answer).__name__` 与 `answer.content` 分别表示什么。核对：前者用于观察对象类型，后者读取本例的固定正文。对象类型名称本身不是模型的回答。

完整脚本 [E03_fake_model.py](examples/E03_fake_model.py) 只打印这两项，不展示长对象结构。固定正文前面保留 fake 标记，避免把演示输出当成审核意见。

### 只改一处

只把预设回答改成另一句文字，原文和模板都保留。预测返回类型与正文分别怎样变化。核对时应看到类型不变，正文按预设改变。

能解释“谁决定了这份固定回答”“`.content` 取出的是什么”，就可以进入任务四。真实模型调用放在后面，它会增加网络、凭据与输出不确定性。

接口依据：[固定聊天模型官方源码](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/language_models/fake_chat_models.py)、[消息官方说明](https://docs.langchain.com/oss/python/langchain/messages)。

## 任务四　先逐步调用，再理解竖线

本节只理解：`|` 把前一步的输出交给下一步。组合后仍然要符合输入输出要求，没有隐藏的共享上下文。

先保留容易观察的逐步写法：

```python
value = prompt.invoke(context)
message = model.invoke(value)
text = parser.invoke(message)
```

`prompt` 是模板，`model` 是固定模型，`parser` 是 `StrOutputParser()`。在本例中，三个返回值依次是提示词值、回答消息、普通字符串。

`StrOutputParser` 用于取得文本输出。它不判断意见对不对，也不执行本项目的 JSON、原文引用和结论关系校验。解析出文字与接受一份业务报告是两件事。

看清逐步调用后，再看组合：

```python
chain = prompt | model | parser
text = chain.invoke(context)
```

这里 `|` 使用可运行组件的组合能力，建立一个顺序结构。创建 `chain` 时只是安排步骤；`chain.invoke(context)` 才执行这次输入。

读取这行代码时，可以暂时在心里还原成前面的三次调用。只要每段输入输出能对应上，竖线就有明确含义，不需要当成一整块新语法背下来。

### 先预测，再核对

预测链的最终返回类型，以及它是否等于逐步取得的 `text`。在本册固定回答设置下，最终都是同一段字符串。完整脚本 [E04_chain.py](examples/E04_chain.py) 逐步执行一次，再用组合执行一次，并比较结果。

两次执行都会走模型调用接口。因为模型只有一份固定回答，看到相同结果；接真实模型以后，执行两次可能产生两次供应商调用，不能为了观察而误以为第二次只是在读取缓存。

### 最容易出错的类型连接

假设某个步骤返回字符串，下一步却按 `context["original_input"]` 访问，它就拿不到预期字典。组成链不等于各组件输入会自动兼容。

当前的模板、模型、解析器适合相接，是因为提示词值能作为模型输入，而模型消息能交给相应文本解析器。以后增加步骤时，也需要逐段检查这些形态。

### 只改一处

先在副本里临时去掉最后的解析器，只运行 `prompt | model`，预测返回类型。确认得到消息对象以后，再恢复解析器，观察变回字符串。这一轮不要改提示词或固定回答。

完成条件：能用三个普通步骤解释竖线表达式，并指出每步交接的对象。暂时不用学习批量、并行、流式和自动重试等方法。

接口依据：[顺序组合官方参考](https://reference.langchain.com/python/langchain-core/runnables/base/RunnableSequence)、[文本解析器官方源码](https://raw.githubusercontent.com/langchain-ai/langchain/master/libs/core/langchain_core/output_parsers/string.py)。

## 任务五　显式把初审保存给 Critic

本节只理解：一份链的返回值不会自动进入下一份链需要的字典。程序仍然需要明确保存它。

先看这一行：

```python
context["analyst_output"] = analyst_chain.invoke(context)
```

右侧把上下文交给 Analyst 链，取得普通字符串；左侧把字符串写入 `analyst_output`。执行后，原文和初审分别有自己的键，Critic 模板才能同时引用。

随后执行：

```python
value = critic_prompt.invoke(context)
messages = value.to_messages()
print(messages[1].content)
```

这一步只观察 Critic 的请求消息，没有让 Critic 模型回答。与项目当前学习任务一样，先把“收到什么”看清楚，再讨论它回答得怎样。

### 一个需要先识别的错误组合

直接写 `analyst_chain | critic_prompt` 时，左侧在本例返回字符串，右侧却需要原文和初审两个变量。原始字典不会因为进入过 Analyst 链就被组合结构自动保留。

解决办法应从数据要求出发：让下一步明确收到同时含原文与初审的结构。当前阶段使用一行显式赋值最容易观察。以后再学更简洁的字段保留与新增方式。

这也帮助理解现有项目的设计。`context` 负责本次审核材料，角色调用负责产生文字。两者通过保存动作连接；框架可以包装调用，但不会替代这份业务责任。

### 先预测，再核对

预测第二条消息中原文和初审分别是什么，哪些文字来自模板，哪些来自字典。完整脚本 [E05_critic_input.py](examples/E05_critic_input.py) 会打印准备好的 Critic 材料。

原文来自创建上下文时的字符串，初审来自固定模型经解析后的返回值，“原文：”“初审：”这样的标签来自 Critic 模板。三种来源能够分别指出，就已经理解了实际数据流。

### 只改一处

第一轮只改原文，固定回答保留，观察 Critic 请求。第二轮再只改 Analyst 的固定回答，原文保留。两轮分别记录变化，不把两种修改混在一次预测里。

因为模型是固定替身，第一轮改原文不会自动改变初审。请求仍应带上新原文和原来的固定初审。这个结果恰好能证明两份数据分别来自哪里。

完成条件：能解释保存语句的左右两侧，并说明为什么直接把 Analyst 的字符串接到一个需要两个变量的模板会出现输入不匹配。

项目对照：[上下文保存位置](../../review_system/workflow.py)、[现有追踪示例](../../examples/core/E05_project_trace.py)。

## 任务六　把相同方法延伸到 Judge

本节只理解：三个角色可以各有提示词与固定模型，仍由普通 Python 明确安排顺序和上下文。

教学流程的核心只有几行：

```python
context["analyst_output"] = analyst.invoke(context)
context["critic_output"] = critic.invoke(context)
final_text = judge.invoke(context)
```

第一行以后，Critic 的模板可以引用初审；第二行以后，Judge 的模板可以引用原文、初审和质疑。最后的返回值保存到 `final_text`，不会自动成为正式业务报告。

完整脚本 [E06_three_roles.py](examples/E06_three_roles.py) 定义一个 `make_chain` 辅助函数，用来建立模板、固定模型和解析器的组合。先把它当成对任务四已学步骤的整理，不要求立刻掌握所有函数参数设计。

三份 system 提示词分别标明 Analyst、Critic、Judge。每份固定模型也单独创建，因此不会由同一个回答列表的内部位置暗中决定当前角色。

### 先预测三个时刻

先写出 Analyst 调用前有哪些键；Critic 调用前增加什么；Judge 调用前再增加什么。这里只观察材料字段，暂不展开模型供应商和服务状态。

核对：第一次只有 `original_input`；第二次增加 `analyst_output`；第三次再增加 `critic_output`。脚本为了方便比较，会排序打印键名，显示顺序不代表角色执行顺序。

然后观察 Judge 的固定 JSON 文字。它明确写证据不足与演示性质，说明这些固定回答没有评价真实材料。程序把它保存为文本，又用 `json.loads` 做一个简单语法层面的观察。

### 这个示例与项目有哪些距离

当前项目还会处理输入上限、审核模式、模型错误、阶段记录、回调、总预算、取消、服务准入以及最终报告契约。教学脚本没有复制这些功能，不能替换业务内核。

尤其是 `json.loads` 不等于 `parse_final_review`。前者能把 JSON 文本读成对象，后者还检查字段、枚举、引用和结论关系。即使演示对象形状接近正式报告，也没有自动完成业务验收。

### 只改一处

只修改 Critic 的固定回答，保留初审和 Judge 固定 JSON。先预测：Judge 调用前字典里的哪项变化，Judge 的固定输出是否变化。核对：`critic_output` 变化，固定 Judge 答案仍按预设返回。

如果要进一步观察 Judge 实际准备的正文，可以在自己的副本中单独保留并调用 Judge 模板。先一次只观察一个中间结果，不急于把所有内部对象都打印出来。

完成条件：能把三次调用对应到输入、保存和下一轮读取，并指出这份示例尚未提供哪些项目保证。核心六个任务到此形成闭合的入门路径。

## 对照项目　组件可以接在哪一层

现有项目的入口、工作流、客户端和契约已经分开。学习 LangChain 时，可以先理解一个组件承担的动作，再看它对应哪一层，避免把整个应用当成一条没有边界的链。

提示词模板对应消息准备。项目当前根据角色生成 system 消息，再把上下文字典序列化成 user 内容。若采用模板，应该核对生成消息是否仍带有原文、模式和需要的前序回答。

聊天模型组件对应模型调用接口。但当前工作流依赖异步 `complete(model=..., messages=...)` 返回文本，而本册固定模型的 `invoke` 返回消息对象。方法名、参数与返回类型并不完全相同。

因此真实接入需要明确适配：配置怎样进入模型，角色消息怎样转换，回答怎样取成字符串，供应商错误怎样变成项目错误，客户端资源由谁管理。这些属于接入设计，不能靠类名相似就省略。

`StrOutputParser` 对应文本输出这一小步，不对应整套报告验证。Judge 文本仍需要进入 `parse_final_review`，只有通过检查才发布正式报告。引用、枚举与跨字段规则继续由项目契约负责。

链式组合可以表示一段固定的处理顺序。但整个 `run_review_async` 还负责阶段、快照、预算与取消。教学上的三行 `.invoke` 只能帮助理解依赖，不能声称自动保留这些运行控制。

同步和异步也要区分。本册为便于观察先使用 `.invoke`；异步组件有 `.ainvoke` 等接口。真实异步性质、异常映射和取消清理仍需按实现检查，不能只把方法名前加一个字母就算完成接入。[Runnable 官方参考](https://reference.langchain.com/python/langchain-core/runnables/base)

当前 FastAPI 服务统一管理审核容量和活动标识，页面经 HTTP 接收完成结果。这些职责在框架组件外依然成立。采用模型封装不等于改变准入协议，也不自动得到跨重启历史。

如果以后做一次最小接入，较清楚的目标是：在独立验证中替换一小段消息准备或模型适配，保持三阶段上下文与错误行为，再用现有回归证明这些约定仍成立。是否正式采用由实际收益决定。

项目定位：[角色](../../review_system/agents.py)、[模型协议](../../review_system/clients.py)、[工作流](../../review_system/workflow.py)、[业务契约](../../review_system/contracts.py)、[服务](../../review_system/service.py)。

## 遇到错误时　先判断卡在哪一段

没有安装核心依赖时，会在导入 `langchain_core` 的位置报找不到模块。此时还没有建立模板，也没有调用任何模型。先检查运行解释器是否是准备好的学习环境。

在一个环境安装、用另一个环境运行，也会出现同样现象。本文统一写完整的 `/home/fanli/ai-engineering/multi-agent/mvp/study/langchain/.venv/bin/python` 路径，就是为了减少激活环境与终端状态带来的混淆。

模板缺少变量时，先比较模板中的变量名与传入字典。比如模板要 `analyst_output`，程序却只保存了 `analysis`，就应修正材料对应关系。不要把未到网络阶段的问题归因于 API Key。

链后半段拿到错误类型时，暂时把竖线拆成分步调用，打印每步的 `type(...).__name__` 与必要内容。确认哪一段开始从字典变成字符串，往往比盯着整条链更容易定位。

消息对象取值方式不同于字典。本例使用 `answer.content`；如果误写成 `answer["content"]`，应先确认对象类型，不能因为两种形式看起来都“有字段”就认为读法相同。

准备消息后没有看到回答，是任务二的正常结果。模板只整理请求；需要模型调用才产生模型消息。创建 `chain` 后没有立即输出，也正常，因为还没有执行 `.invoke(...)`。

改了原文但固定回答不变，也是本册预期。要观察传入值，应检查模板消息；要让固定回答变化，应修改预设列表；要观察真实生成变化，则进入以后单独验证的真实模型阶段。

异常可能在链的任一步出现，后续正常步骤通常不会继续。本项目还会把异常附上阶段与部分结果；教学例子没有完整复制这种错误封装，读 traceback 时需先看实际文件和位置。

卡住时可以留下四项信息：运行的文件路径、使用的解释器、报错行、你原来预测的输入与返回类型。解决这一处后再继续，不需要同时重装所有包或重写整份示例。

## 后续预览　什么时候再学习 Agent

六个任务完成以后，已经能够理解显式顺序链。下一阶段如果需要模型根据工具结果决定是否继续，才进入完整 Agent 的运行方式。

当前官方文档提供 `create_agent` 入口，将模型、工具、提示词等组成运行结构。这个入口解决的问题比本册的模板和固定链更大，也会增加工具调用、消息历史和停止条件等新概念。[官方 Agent 概览](https://docs.langchain.com/oss/python/langchain/overview)

对本项目而言，Analyst、Critic、Judge 的顺序已经由需求固定，并不因为开始学 LangChain 就必须改成模型自主选择。应先说明新的自由度准备解决哪一种现有不足。

比较清楚的后续学习目标，可以是让一个独立练习中的模型选择只读工具，再根据工具返回结果形成回答。那时再观察工具参数、执行结果和下一轮消息，而不是一开始加入多个角色和复杂流程。

学习完成证据也应具体：能指出谁选择了工具，谁实际执行函数，结果怎样返回模型，以及什么条件使循环停止。只看到最终回答，无法证明已经理解这些环节。

如果只是想让 Critic 得到原文与初审，当前显式上下文已经解决了这个问题。保持已有方法清楚，再增加新能力，有助于判断框架真正帮你省下了哪一类工作。

本册不把 Agent 预览计为已完成任务。它是下一阶段的方向，等六个输入输出问题能够解释后再进入。

## 后续预览　RAG 应接在材料的哪一侧

RAG 可以为回答补充从资料中检索到的上下文。学习时首先关注资料如何进入请求，再逐渐认识切分、索引、检索和评估，而不是先记住一组数据库名称。[官方检索概念](https://docs.langchain.com/oss/python/deepagents/retrieval)

把它对应到本项目，可以设想增加一份 `evidence_context`，保存从项目规范中找到的资料。原文仍是 `original_input`，初审与质疑仍是前序输出，两种来源要有清楚标记。

这个字段只是未来设计示意，当前工作流没有实现它。即使将资料拼入提示词，也还要解释来源、无结果时的行为，以及模型意见是否确实得到资料支持。

当前问题引用只允许指向用户原文。如果以后要引用知识资料，就需要另行定义来源标识和资料位置，不能直接沿用原文的 `start`、`end` 来表示一份外部文档。

适合你的下一步检索练习，可以先用少量本地文字与明确规则挑选资料，观察哪些片段进入模型请求。等这条数据流能解释，再讨论向量表示、检索质量和重排序。

本项目暂不引入数据库或 Docker。阅读 RAG 教程中的相关章节，不等于现在就要扩大项目依赖。学习可以先建立概念与小例子，再根据需求选择实现。

Agent 与 RAG 也能分别学习。一条固定流程可以使用检索，一个工具型 Agent 也不一定需要知识库。回到具体需求判断，能减少多个新名词同时进入一个练习的负担。

## 附录一　电脑验证的准备与示例清单

阅读正文不需要安装。只有准备运行 E01–E06 时，才需要核心包。配套说明位于 [示例目录](examples/README.md)。本项目主运行依赖没有增加 LangChain。

E00 使用标准库，可以直接用现有项目解释器运行。后续脚本使用独立学习环境，避免把练习安装与原项目的依赖快照混在一起。

首次准备时，在终端执行：

```bash
python3 -m venv /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/.venv
/home/fanli/ai-engineering/multi-agent/mvp/study/langchain/.venv/bin/python -m pip install -r /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/examples/requirements.txt
```

依赖文件只声明 `langchain-core>=1,<2`，表示本册采用核心包 1.x 公开组件。它不是精确版本锁定；实际安装到的版本应在自己的运行记录中注明。

安装阶段需要包源网络。安装好以后，本册的普通函数、模板与固定模型示例本身不访问供应商，不需要模型凭据。所有模型回答都写有 fake 或固定标记。

准备好环境后，先运行任务一：

```bash
/home/fanli/ai-engineering/multi-agent/mvp/study/langchain/.venv/bin/python /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/examples/E01_runnable.py
```

需要亲手修改时，先建立自己的副本：

```bash
mkdir -p /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/practice
cp -n /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/examples/E01_runnable.py /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/practice/E01_runnable.py
```

再运行副本，而不是仍然运行原文件：

```bash
/home/fanli/ai-engineering/multi-agent/mvp/study/langchain/.venv/bin/python /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/practice/E01_runnable.py
```

`cp -n` 避免覆盖已有同名副本。若副本已经存在，先查看自己的修改，再决定本轮预测依据。不要为了重新开始而直接覆盖自己的记录。

示例名称与正文对应：

- [E00](examples/E00_plain_context.py)：普通 Python 的初审保存与 Critic 输入。
- [E01](examples/E01_runnable.py)：普通函数与 `.invoke`。
- [E02](examples/E02_prompt.py)：模板变量与消息列表。
- [E03](examples/E03_fake_model.py)：消息对象与回答正文。
- [E04](examples/E04_chain.py)：分步调用与链式组合。
- [E05](examples/E05_critic_input.py)：显式保存初审，观察 Critic 材料。
- [E06](examples/E06_three_roles.py)：三角色教学顺序和固定 JSON 文本。

只运行当前对应的一份即可。每份脚本都包含自己的导入和 `main`，不需要手动复制前面章节中的变量到同一终端会话。

## 附录二　每次怎样留下有效学习证据

一份短记录可以只包含四项：本次只理解什么；运行前怎样预测；实际看到了什么；现在能解释哪一处。没有必要因为示例运行成功就立即进入下一项。

以任务五为例，可以写：“本次观察 Critic 请求；预测原文和初审分别进入第二条消息；修改原文后只有原文部分变化；能够指出初审是上一条链返回后显式保存的。”

如果暂时不能解释，可以写“已运行，尚不能说明返回值类型”。这仍然是准确的进度信息，比把整节标成掌握更利于下次安排。

如果希望 AI 协助，问题也可以保持局部。例如：请只解释 `context["analyst_output"] = analyst_chain.invoke(context)`，分别指出右侧输入、返回值与左侧保存位置，然后给一个只改一处的验证。

另一种有效请求是：我运行的是这个文件，这一行报错，原本预测返回字典，实际返回字符串；请先指出数据在哪一步改变类型，暂不重写完整程序。

你已经有的学习路线强调小变体验证，因此本册保留相同节奏。文档不会代替本人更新“今天”，也不会把未来的 Agent 或 RAG 预览登记为任务完成。

## 附录三　术语、资料与核验范围

Runnable：可以按统一接口执行的步骤。在任务一中，它包装一个普通函数。不要仅从名称推断其中必然有模型。

invoke：同步执行一次组件调用。输入和返回类型由对应组件决定，不能把所有 `.invoke` 都理解成“输入字符串，输出字符串”。

提示词模板：根据变量准备消息。模板定义、模板填值和模型生成是不同动作，分别观察更容易理解。

消息：带角色与内容的信息对象。本册先观察 system、human 和 AI 回答，其他类型留到需要工具与历史时认识。

解析器：把一个输出转换成下一步需要的形态。本册的文本解析器不承担本项目完整报告的业务检查。

链：按一定关系组合步骤。顺序链仍需要前后输入输出匹配；原文与中间结果是否保留，由你的结构设计决定。

固定模型：用预置回答模拟模型接口。它帮助验证数据流，不能用来判断审核质量，也不会随着提示词变化自动思考。

状态：程序保存的当前材料与运行信息。示例中的字典、项目中的运行快照、未来可能的对话历史，分别有自己的结构和生命周期。

建议按需要查官方资料：

- [LangChain 概览](https://docs.langchain.com/oss/python/langchain/overview)：了解框架当前定位及 Agent 入口。
- [RunnableLambda](https://reference.langchain.com/python/langchain-core/runnables/base/RunnableLambda)：对应任务一。
- [ChatPromptTemplate](https://reference.langchain.com/python/langchain-core/prompts/chat/ChatPromptTemplate)：对应任务二。
- [消息说明](https://docs.langchain.com/oss/python/langchain/messages)：对应任务三。
- [顺序组合](https://reference.langchain.com/python/langchain-core/runnables/base/RunnableSequence)：对应任务四。
- [固定模型源码](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/language_models/fake_chat_models.py)：核对预设回答行为。
- [文本解析器源码](https://github.com/langchain-ai/langchain/blob/master/libs/core/langchain_core/output_parsers/string.py)：核对文本转换职责。

核验分三层记录：第一，接口与导入路径对照官方文档和源码；第二，脚本进行 Python 语法检查，E00 可用现有环境执行；第三，E01–E06 需要安装核心依赖后执行。本次主环境没有 LangChain，未把第三层记为已完成验收。

现有项目的 pytest 回归另行执行，只证明其对应的程序行为，不替代 LangChain 示例或真实供应商连通性。遇到版本差异时，先保留解释器、已安装核心包版本、报错位置和实际输出，再对照当前官方参考核查。
