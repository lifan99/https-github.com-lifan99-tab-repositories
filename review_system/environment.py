"""Load project-local environment defaults at application startup."""

from pathlib import Path

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent.parent


def load_project_env() -> None:
    """Load only the project's .env, preserving existing environment values."""
    load_dotenv(dotenv_path=PROJECT_ROOT / ".env", override=False, verbose=False)
