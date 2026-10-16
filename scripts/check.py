"""Run the same offline checks locally and in CI with the current interpreter."""

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
COMMANDS = [
    ["-m", "ruff", "check", "app.py", "review_system", "tests", "scripts"],
    ["scripts/check_docs.py"],
    ["-m", "pytest", "-q"],
    ["-m", "pytest", "-q", "docs/two-hour-course/examples/E07_test_workflow.py",
     "docs/two-hour-course/examples/A02_test_callback_solution.py",
     "docs/two-hour-course/examples/A03_test_request_solution.py"],
    ["-m", "pytest", "-q", "docs/http-practice/test_exercises.py"],
    ["-m", "pip", "check"],
]


def main():
    env = {**os.environ, "HTTP_PRACTICE_IMPL": "solution"}
    for arguments in COMMANDS:
        print("Running:", sys.executable, *arguments, flush=True)
        result = subprocess.run([sys.executable, *arguments], cwd=ROOT, env=env)
        if result.returncode:
            return result.returncode
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
