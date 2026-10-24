"""按需读取供应商配置，校验端点、模型与时间预算；导入时不读取环境。"""

import math
import os
from dataclasses import dataclass, field
from urllib.parse import urlsplit


def validate_seconds(value: float, name: str) -> None:
    """时间预算只接受有限正数；显式排除作为 int 子类的 bool。"""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite positive number.")
    try:
        valid = math.isfinite(value) and value > 0
    except OverflowError:
        valid = False
    if not valid:
        raise ValueError(f"{name} must be a finite positive number.")


def env_seconds(name: str, default: str) -> float:
    """读取秒数配置并统一校验；未设置时才使用默认值，空字符串会报错。"""
    try:
        value = float(os.getenv(name, default))
    except ValueError as exc:
        raise ValueError(f"{name} must be a finite positive number.") from exc
    validate_seconds(value, name)
    return value


def validate_base_url(value: str, name: str) -> None:
    """限制为有效 HTTP(S) 根地址，拒绝内嵌凭据、查询参数、片段及非法端口。"""
    message = f"{name} must be an HTTP(S) base URL without credentials, query or fragment, with a valid port."
    try:
        parsed = urlsplit(value)
        valid = (
            parsed.scheme in {"http", "https"} and bool(parsed.hostname)
            and parsed.username is None and parsed.password is None
            and not parsed.query and not parsed.fragment
        )
        parsed.port  # 读取属性会触发端口的数字格式及范围校验。
    except ValueError as exc:
        raise ValueError(message) from exc
    if not valid:
        raise ValueError(message)


@dataclass(frozen=True)
class Settings:
    """构造时校验三类时间预算；from_env 额外校验真实供应商配置。

    直接构造允许注入使用空密钥的离线客户端；若直接用于真实调用，调用方需校验供应商、
    端点、密钥及模型名称。api_key 不出现在对象的常规字符串表示中。
    """

    provider: str
    base_url: str
    api_key: str = field(repr=False)
    model: str
    analyst_model: str
    critic_model: str
    judge_model: str
    timeout_seconds: float = 60
    model_timeout_seconds: float = 60
    total_timeout_seconds: float = 150

    def __post_init__(self):
        """无论配置来自环境还是直接构造，都拒绝非法时间预算。"""
        for name in ("timeout_seconds", "model_timeout_seconds", "total_timeout_seconds"):
            validate_seconds(getattr(self, name), name)

    @classmethod
    def from_env(cls) -> "Settings":
        """读取所选供应商配置；各角色可覆盖默认模型，缺少必需配置时立即报错。"""
        provider = os.getenv("REVIEW_PROVIDER", "qwen").strip().lower()
        if provider not in {"qwen", "deepseek"}:
            raise ValueError("REVIEW_PROVIDER must be qwen or deepseek.")
        prefix = provider.upper()
        key = os.getenv(f"{prefix}_API_KEY", "").strip()
        if not key:
            raise ValueError(f"Set {prefix}_API_KEY before running a review.")
        default_url = (
            "https://dashscope-intl.aliyuncs.com/compatible-mode/v1"
            if provider == "qwen" else "https://api.deepseek.com/v1"
        )
        base_url = os.getenv(f"{prefix}_BASE_URL", default_url).strip().rstrip("/")
        validate_base_url(base_url, f"{prefix}_BASE_URL")
        model = os.getenv(f"{prefix}_MODEL", "qwen-plus" if provider == "qwen" else "deepseek-flash").strip()
        if not model:
            raise ValueError(f"{prefix}_MODEL must not be empty.")
        timeout = env_seconds("REVIEW_TIMEOUT_SECONDS", "60")
        # 网络操作超时、单次模型预算、整次审核预算分别控制不同层次的等待。
        return cls(
            provider=provider, base_url=base_url, api_key=key, model=model,
            analyst_model=os.getenv("ANALYST_MODEL", "").strip() or model,
            critic_model=os.getenv("CRITIC_MODEL", "").strip() or model,
            judge_model=os.getenv("JUDGE_MODEL", "").strip() or model,
            timeout_seconds=timeout,
            model_timeout_seconds=env_seconds("REVIEW_MODEL_TIMEOUT_SECONDS", "60"),
            total_timeout_seconds=env_seconds("REVIEW_TOTAL_TIMEOUT_SECONDS", "150"),
        )
