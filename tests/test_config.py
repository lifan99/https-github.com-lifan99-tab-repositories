"""配置回归：覆盖供应商默认值、角色模型覆盖及非法端点和预算的提前拒绝。"""

import os
from unittest.mock import patch

import pytest

from review_system.config import Settings


@pytest.mark.parametrize("provider, model, base_url", [
    ("qwen", "qwen-plus", "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"),
    ("deepseek", "deepseek-flash", "https://api.deepseek.com/v1"),
])
def test_provider_defaults(provider, model, base_url):
    """分别验证供应商默认端点及默认模型。"""
    env = {"REVIEW_PROVIDER": provider, f"{provider.upper()}_API_KEY": "test-placeholder"}
    with patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    assert settings.base_url == base_url
    assert settings.model == model
    assert settings.analyst_model == settings.critic_model == settings.judge_model == model
    assert settings.model_timeout_seconds == 60
    assert settings.total_timeout_seconds == 150


@pytest.mark.parametrize("provider", ["qwen", "deepseek"])
def test_provider_and_stage_model_configuration(provider):
    """环境可覆盖供应商、默认模型及各角色模型，并保留密钥隐藏规则。"""
    prefix = provider.upper()
    env = {
        "REVIEW_PROVIDER": provider,
        f"{prefix}_API_KEY": "test-placeholder",
        f"{prefix}_BASE_URL": "https://example.invalid/v1/",
        f"{prefix}_MODEL": "custom-model",
        "CRITIC_MODEL": "custom-critic",
        "REVIEW_TIMEOUT_SECONDS": "15",
        "REVIEW_MODEL_TIMEOUT_SECONDS": "25",
        "REVIEW_TOTAL_TIMEOUT_SECONDS": "45",
    }
    with patch.dict(os.environ, env, clear=True):
        settings = Settings.from_env()
    assert settings.provider == provider
    assert settings.base_url == "https://example.invalid/v1"
    assert settings.analyst_model == settings.judge_model == "custom-model"
    assert settings.critic_model == "custom-critic"
    assert settings.timeout_seconds == 15
    assert settings.model_timeout_seconds == 25
    assert settings.total_timeout_seconds == 45
    assert settings.api_key not in repr(settings)


@pytest.mark.parametrize("env, message", [
    ({}, "QWEN_API_KEY"),
    ({"REVIEW_PROVIDER": "unknown"}, "REVIEW_PROVIDER"),
    ({"QWEN_API_KEY": "test-placeholder", "REVIEW_TIMEOUT_SECONDS": "0"}, "positive number"),
    ({"QWEN_API_KEY": "test-placeholder", "REVIEW_TIMEOUT_SECONDS": "nan"}, "positive number"),
    ({"QWEN_API_KEY": "test-placeholder", "REVIEW_TIMEOUT_SECONDS": "bad"}, "positive number"),
    ({"QWEN_API_KEY": "test-placeholder", "QWEN_BASE_URL": "invalid"}, "HTTP"),
    ({"QWEN_API_KEY": "test-placeholder", "QWEN_MODEL": " "}, "must not be empty"),
])
def test_invalid_configuration(env, message):
    """缺少必需值或供应商非法时立即报错。"""
    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(ValueError, match=message):
            Settings.from_env()


@pytest.mark.parametrize("variable", ["REVIEW_TIMEOUT_SECONDS", "REVIEW_MODEL_TIMEOUT_SECONDS", "REVIEW_TOTAL_TIMEOUT_SECONDS"])
@pytest.mark.parametrize("value", ["0", "-1", "nan", "inf", "bad"])
def test_invalid_timeout_environment(variable, value):
    """拒绝空值、非数值、非有限值及非正时间预算。"""
    with patch.dict(os.environ, {"QWEN_API_KEY": "synthetic-key", variable: value}, clear=True):
        with pytest.raises(ValueError, match=variable):
            Settings.from_env()


@pytest.mark.parametrize("url", [
    "https://user:private-password@example.invalid/v1", "http://localhost:bad", "http://localhost:99999",
    "http://[invalid", "https://example.invalid/v1?private-query=1", "https://example.invalid/#private",
])
def test_invalid_provider_url_is_rejected_before_http_without_exposing_url(url):
    """非法供应商地址在 HTTP 调用前拒绝，错误中不回显敏感地址。"""
    with patch.dict(os.environ, {"QWEN_API_KEY": "synthetic-key", "QWEN_BASE_URL": url}, clear=True):
        with pytest.raises(ValueError) as caught:
            Settings.from_env()
    assert "QWEN_BASE_URL" in str(caught.value)
    assert "private" not in str(caught.value)


def test_unrepresentable_integer_budget_is_a_configuration_error():
    """过大整数引发的转换溢出归类为配置错误。"""
    with pytest.raises(ValueError, match="finite positive"):
        Settings("qwen", "https://example.invalid", "synthetic", "m", "a", "c", "j", timeout_seconds=10**1000)
