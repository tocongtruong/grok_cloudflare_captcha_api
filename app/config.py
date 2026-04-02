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
            api_key=(os.getenv("API_KEY", "") or "").strip(),
        )
