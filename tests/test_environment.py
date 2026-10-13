import os
import runpy
import sys
from unittest.mock import MagicMock, patch

from review_system import environment
from review_system.config import Settings


def test_loader_targets_project_root_without_reading_real_env():
    with patch("review_system.environment.load_dotenv") as load:
        environment.load_project_env()
    load.assert_called_once_with(
        dotenv_path=environment.PROJECT_ROOT / ".env", override=False, verbose=False,
    )


def test_application_loads_environment_before_rendering():
    streamlit = MagicMock()
    streamlit.button.return_value = False
    streamlit.session_state = {}
    with patch.dict(sys.modules, {"streamlit": streamlit}):
        with patch("review_system.environment.load_project_env") as load:
            streamlit.set_page_config.side_effect = lambda **kwargs: load.assert_called_once_with()
            runpy.run_path(str(environment.PROJECT_ROOT / "app.py"))
            load.assert_called_once_with()


def test_dotenv_defaults_and_environment_priority(tmp_path, monkeypatch, capsys, caplog):
    # Only synthetic fixtures are read, never the actual project .env.
    monkeypatch.setattr(environment, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text(
        "REVIEW_PROVIDER=deepseek\n"
        "DEEPSEEK_API_KEY=synthetic-fixture-key\n"
        "DEEPSEEK_MODEL=dotenv-model\n"
        "CRITIC_MODEL=dotenv-critic\n"
        "JUDGE_MODEL=dotenv-judge\n",
        encoding="utf-8",
    )
    with patch.dict(os.environ, {"DEEPSEEK_MODEL": "shell-model", "JUDGE_MODEL": ""}, clear=True):
        environment.load_project_env()
        settings = Settings.from_env()
        assert settings.provider == "deepseek"
        assert settings.api_key == "synthetic-fixture-key"
        assert settings.model == settings.analyst_model == "shell-model"
        assert settings.critic_model == "dotenv-critic"
        assert os.environ["JUDGE_MODEL"] == ""
        assert settings.judge_model == "shell-model"
        assert settings.api_key not in repr(settings)
    captured = capsys.readouterr()
    assert captured.out == captured.err == ""
    assert not caplog.records


def test_existing_api_key_is_preserved(tmp_path, monkeypatch):
    monkeypatch.setattr(environment, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text("QWEN_API_KEY=synthetic-file-value\n", encoding="utf-8")
    with patch.dict(os.environ, {"QWEN_API_KEY": "synthetic-shell-value"}, clear=True):
        environment.load_project_env()
        assert os.environ["QWEN_API_KEY"] == "synthetic-shell-value"


def test_missing_project_env_does_not_search_working_directory(tmp_path, monkeypatch):
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr(environment, "PROJECT_ROOT", project_root)
    # A .env in the working directory must not be used as a fallback.
    (tmp_path / ".env").write_text("QWEN_API_KEY=synthetic-unrelated-value\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with patch.dict(os.environ, {"QWEN_MODEL": "existing-model"}, clear=True):
        environment.load_project_env()
        assert dict(os.environ) == {"QWEN_MODEL": "existing-model"}
