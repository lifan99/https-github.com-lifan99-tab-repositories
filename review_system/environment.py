"""应用启动时加载项目根目录的 .env，保留进程中已有的环境变量。"""

from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_env() -> None:
    """只读取项目根目录的 .env；已有环境变量优先，即使其值为空也不覆盖。"""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False, verbose=False)
