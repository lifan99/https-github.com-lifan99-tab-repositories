# LangChain 入门示例

配套 [项目学习手册](../LangChain项目学习手册.md)。按 E00 至 E06 顺序使用，每次只运行一份。

E00 仅依赖标准库；E01–E06 需要 `langchain-core`。所有示例使用普通函数或固定回答，不访问供应商，不需要 API Key。主项目依赖和业务源码保持原样。

在终端，先准备独立学习环境：

```bash
python3 -m venv /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/.venv
/home/fanli/ai-engineering/multi-agent/mvp/study/langchain/.venv/bin/python -m pip install -r /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/examples/requirements.txt
```

安装需要包源网络。准备好以后，示例执行本身可以离线：

```bash
/home/fanli/ai-engineering/multi-agent/mvp/study/langchain/.venv/bin/python /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/examples/E01_runnable.py
```

更换文件名即可运行后续任务。E00 只用标准库，从任意目录执行下面的命令即可：

```bash
python3 /home/fanli/ai-engineering/multi-agent/mvp/study/langchain/examples/E00_plain_context.py
```

不要把练习依赖直接安装到主项目环境。

E06 是教学顺序演示，只做 JSON 语法解析，没有复刻项目的领域报告校验、阶段记录、总预算、取消和服务准入。它不能替换 `review_system/workflow.py`。

编写时已对照 LangChain 官方文档与源码，并可进行 Python 语法检查。本机主环境未安装 LangChain；E01–E06 尚未做安装依赖后的执行验收。依赖范围用于练习兼容约束，不是锁定版本快照。
