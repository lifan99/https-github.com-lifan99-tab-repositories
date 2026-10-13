"""Provider configuration, read only when requested."""

from dataclasses import dataclass, field
import math
import os
from urllib.parse import urlsplit


@dataclass(frozen=True)
class Settings:
    provider: str
    base_url: str
    api_key: str = field(repr=False)
    model: str
    analyst_model: str
    critic_model: str
    judge_model: str
    timeout_seconds: float = 60

    @classmethod
    def from_env(cls) -> "Settings":
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
        parsed = urlsplit(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.query or parsed.fragment:
            raise ValueError(f"{prefix}_BASE_URL must be an HTTP(S) base URL without query or fragment.")
        model = os.getenv(f"{prefix}_MODEL", "qwen-plus" if provider == "qwen" else "deepseek-flash").strip()
        if not model:
            raise ValueError(f"{prefix}_MODEL must not be empty.")
        try:
            timeout = float(os.getenv("REVIEW_TIMEOUT_SECONDS", "60"))
        except ValueError as exc:
            raise ValueError("REVIEW_TIMEOUT_SECONDS must be a positive number.") from exc
        if not math.isfinite(timeout) or timeout <= 0:
            raise ValueError("REVIEW_TIMEOUT_SECONDS must be a positive number.")
        return cls(
            provider=provider, base_url=base_url, api_key=key, model=model,
            analyst_model=os.getenv("ANALYST_MODEL", "").strip() or model,
            critic_model=os.getenv("CRITIC_MODEL", "").strip() or model,
            judge_model=os.getenv("JUDGE_MODEL", "").strip() or model,
            timeout_seconds=timeout,
        )
