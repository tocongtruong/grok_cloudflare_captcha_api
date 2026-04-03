import os
from dataclasses import dataclass


def parse_int(value: str, default: int, min_value: int) -> int:
    try:
        parsed = int(str(value).strip())
    except (TypeError, ValueError):
        return max(default, min_value)
    return max(parsed, min_value)


def parse_bool(value: str, default: bool = False) -> bool:
    if value is None:
        return default
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    return default


@dataclass
class Settings:
    flaresolverr_url: str
    target_url: str
    timeout_sec: int
    base_proxy_url: str
    warp_auto_priority: bool
    warp_proxy_url: str
    auto_http_proxy_enabled: bool
    auto_http_proxy_port: int
    auto_http_proxy_user: str
    auto_http_proxy_password: str
    public_proxy_url: str
    api_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        return cls(
            flaresolverr_url=(os.getenv("FLARESOLVERR_URL", "") or "").strip(),
            target_url=(os.getenv("TARGET_URL", "https://grok.com") or "https://grok.com").strip(),
            timeout_sec=parse_int(os.getenv("TIMEOUT_SEC", "90"), default=90, min_value=10),
            base_proxy_url=(os.getenv("BASE_PROXY_URL", "") or "").strip(),
            warp_auto_priority=parse_bool(os.getenv("WARP_AUTO_PRIORITY", "true"), default=True),
            warp_proxy_url=(os.getenv("WARP_PROXY_URL", "socks5://warp:1080") or "socks5://warp:1080").strip(),
            auto_http_proxy_enabled=parse_bool(os.getenv("AUTO_HTTP_PROXY_ENABLED", "true"), default=True),
            auto_http_proxy_port=parse_int(os.getenv("AUTO_HTTP_PROXY_PORT", "3128"), default=3128, min_value=1),
            auto_http_proxy_user=(os.getenv("AUTO_HTTP_PROXY_USER", "") or "").strip(),
            auto_http_proxy_password=(os.getenv("AUTO_HTTP_PROXY_PASSWORD", "") or "").strip(),
            public_proxy_url=(os.getenv("PUBLIC_PROXY_URL", "") or "").strip(),
            api_key=(os.getenv("API_KEY", "") or "").strip(),
        )
