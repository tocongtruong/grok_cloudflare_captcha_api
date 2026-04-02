from __future__ import annotations

from typing import Any

import requests


class QuotaError(RuntimeError):
    pass


AUTH_ERROR_KEYWORDS = ("unauthorized", "not logged in", "unauthenticated", "bad-credentials")


def _build_headers(cookie_header: str, user_agent: str) -> dict[str, str]:
    return {
        "accept": "*/*",
        "content-type": "application/json",
        "origin": "https://grok.com",
        "referer": "https://grok.com/",
        "user-agent": user_agent,
        "cookie": cookie_header,
    }


def _build_proxies(proxy_url: str) -> dict[str, str] | None:
    value = (proxy_url or "").strip()
    if not value:
        return None
    return {
        "http": value,
        "https": value,
    }


def inspect_token_upstream(
    *,
    cookie_header: str,
    user_agent: str,
    timeout_sec: int,
    proxy_url: str = "",
) -> dict[str, Any]:
    endpoint = "https://grok.com/rest/rate-limits"
    payload = {
        "requestKind": "DEFAULT",
        "modelName": "grok-4-1-thinking-1129",
    }

    headers = _build_headers(cookie_header, user_agent)
    kwargs: dict[str, Any] = {
        "json": payload,
        "headers": headers,
        "timeout": timeout_sec,
    }

    proxies = _build_proxies(proxy_url)
    if proxies:
        kwargs["proxies"] = proxies

    try:
        response = requests.post(endpoint, **kwargs)
    except requests.RequestException as exc:
        raise QuotaError(f"request to rate-limits failed: {exc}") from exc

    status_code = int(response.status_code)
    body_text = (response.text or "")[:2000]
    body_lower = body_text.lower()
    content_type = (response.headers.get("Content-Type") or "").lower()
    server_header = (response.headers.get("Server") or "").lower()

    quota: dict[str, Any] = {}
    if "application/json" in content_type:
        try:
            parsed = response.json()
            if isinstance(parsed, dict):
                quota = parsed
        except ValueError:
            quota = {}

    is_cloudflare = "challenge-platform" in body_lower or (
        "cloudflare" in server_header and "application/json" not in content_type
    )

    token_expired = False
    reason = "active"

    if status_code == 200:
        token_expired = False
        reason = "active"
    elif status_code == 401:
        if "application/json" in content_type and any(k in body_lower for k in AUTH_ERROR_KEYWORDS):
            token_expired = True
            reason = "token_expired"
        elif is_cloudflare:
            token_expired = False
            reason = "cloudflare_blocked"
        else:
            token_expired = False
            reason = "auth_unknown"
    elif is_cloudflare:
        token_expired = False
        reason = "cloudflare_blocked"
    else:
        token_expired = False
        reason = "upstream_error"

    return {
        "status": "ok",
        "quota": quota,
        "token_expired": token_expired,
        "reason": reason,
        "upstream_status": status_code,
        "is_cloudflare": is_cloudflare,
    }
