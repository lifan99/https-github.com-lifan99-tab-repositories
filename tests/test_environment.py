"""环境加载回归：隔离真实 .env，验证项目路径定位与已有变量优先级。"""

import os
import runpy
import sys
from unittest.mock import MagicMock, patch

from review_system import environment
from review_system.config import Settings


def test_loader_targets_project_root_without_reading_real_env():
    """拦截加载函数，确认只定位项目根目录且不读取真实配置。"""
    with patch("review_system.environment.load_dotenv") as load:
        environment.load_project_env()
    load.assert_called_once_with(
        dotenv_path=environment.PROJECT_ROOT / ".env", override=False, verbose=False,
    )


def test_application_loads_environment_before_rendering():
    """页面渲染前先加载项目环境默认值。"""
    streamlit = MagicMock()
    streamlit.button.return_value = False
    streamlit.session_state = {}
    with patch.dict(sys.modules, {"streamlit": streamlit}):
        with patch("review_system.environment.load_project_env") as load:
            streamlit.set_page_config.side_effect = lambda **kwargs: load.assert_called_once_with()
            runpy.run_path(str(environment.PROJECT_ROOT / "app.py"))
            load.assert_called_once_with()


def test_dotenv_defaults_and_environment_priority(tmp_path, monkeypatch, capsys, caplog):
    # 只读取临时构造的配置样本，不访问项目实际的 .env。
    """临时 .env 补全缺省值，进程已有值优先。"""
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
    """已存在的 API Key 不会被 .env 覆盖。"""
    monkeypatch.setattr(environment, "PROJECT_ROOT", tmp_path)
    (tmp_path / ".env").write_text("QWEN_API_KEY=synthetic-file-value\n", encoding="utf-8")
    with patch.dict(os.environ, {"QWEN_API_KEY": "synthetic-shell-value"}, clear=True):
        environment.load_project_env()
        assert os.environ["QWEN_API_KEY"] == "synthetic-shell-value"


def test_missing_project_env_does_not_search_working_directory(tmp_path, monkeypatch):
    """项目 .env 不存在时，不误加载当前工作目录的其他文件。"""
    project_root = tmp_path / "project"
    project_root.mkdir()
    monkeypatch.setattr(environment, "PROJECT_ROOT", project_root)
    # 项目配置缺失时，不使用当前工作目录的 .env 作为备用配置。
    (tmp_path / ".env").write_text("QWEN_API_KEY=synthetic-unrelated-value\n", encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    with patch.dict(os.environ, {"QWEN_MODEL": "existing-model"}, clear=True):
        environment.load_project_env()
        assert dict(os.environ) == {"QWEN_MODEL": "existing-model"}
