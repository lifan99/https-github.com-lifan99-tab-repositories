"""用当前 Python 解释器执行本地和 CI 共用的离线检查，任一检查失败即停止。"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = [
    ["-m", "ruff", "check", "app.py", "review_system", "tests", "scripts"],
    ["scripts/check_docs.py"],
    ["-m", "pytest", "-q"],
    ["-m", "pytest", "-q", "examples/core/E07_test_workflow.py",
     "examples/core/A02_test_callback_solution.py",
     "examples/core/A03_test_request_solution.py"],
    ["-m", "pytest", "-q", "examples/http-practice/test_exercises.py"],
    ["-m", "pip", "check"],
]


def main():
    """依次执行检查并原样返回首个失败退出码，确保本地与 CI 使用相同入口。"""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--include-personal", action="store_true")
    args = parser.parse_args()
    commands = [list(command) for command in COMMANDS]
    if args.include_personal:
        commands[1].append("--include-personal")
        commands.append(["-m", "pytest", "-q", str(ROOT.parent.parent / "learning/python/practice")])
    # 练习文件保留 TODO，统一回归运行参考实现，避免把尚未完成的作业当成工程失败。
    env = {**os.environ, "HTTP_PRACTICE_IMPL": "solution"}
    for arguments in commands:
        print("Running:", sys.executable, *arguments, flush=True)
        result = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
