# HTTP 编程练习

返回 [文档总导航](../../docs/README.md)，其他示例见 [项目示例](../README.md)。本目录对应 HTTP 练习 Q07—Q09，基础讲解见 [HTTP 基础](../../docs/technical/HTTP基础.md)，题目入口见 [练习册](../../study/练习册.md)。

|文件|用途|
|---|---|
|[exercise.py](exercise.py)|作业模板，包含三个待完成的 TODO|
|[test_exercises.py](test_exercises.py)|离线验收测试；默认检查自己的作业实现|
|[solution.py](solution.py)|已有参考实现，独立完成后核对|

从项目根目录运行自己的实现：

```bash
.venv/bin/python -m pytest -q examples/http-practice/test_exercises.py
```

未完成 TODO 时测试失败是预期状态。需要验证现有参考实现时，显式选择：

```bash
HTTP_PRACTICE_IMPL=solution .venv/bin/python -m pytest -q examples/http-practice/test_exercises.py
```

该练习属于已有项目 HTTP 教学，不是计算机系统课程的 Lab 2 参考答案；后者的独立规格在 系统实验册（基础资料：`~/ai-engineering/learning/computer-systems/02-labs.md`）。
