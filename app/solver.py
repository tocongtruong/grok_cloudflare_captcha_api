import re
from typing import Any

import requests


class SolveError(RuntimeError):
    pass


def detect_browser(user_agent: str) -> str:
    match = re.search(r"Chrome/(\d+)", user_agent or "")
    if match:
        return f"chrome{match.group(1)}"
    return "chrome120"


def cookie_value(cookies: list[dict[str, Any]], key: str) -> str:
    for item in cookies:
        if item.get("name") == key:
            return str(item.get("value") or "")
    return ""


def cookie_string(cookies: list[dict[str, Any]]) -> str:
    parts = []
    for item in cookies:
        name = item.get("name")
        value = item.get("value")
        if name and value is not None:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


def cookie_map(cookies: list[dict[str, Any]]) -> dict[str, str]:
    mapped: dict[str, str] = {}
    for item in cookies:
        name = item.get("name")
        value = item.get("value")
        if name and value is not None:
            mapped[str(name)] = str(value)
    return mapped


def solve_cloudflare(
    *,
    flaresolverr_url: str,
    target_url: str,
    timeout_sec: int,
    proxy_url: str = "",
) -> dict[str, Any]:
    if not flaresolverr_url:
        raise SolveError("FLARESOLVERR_URL is empty")

    endpoint = f"{flaresolverr_url.rstrip('/')}/v1"
    payload: dict[str, Any] = {
        "cmd": "request.get",
        "url": target_url,
        "maxTimeout": int(timeout_sec * 1000),
    }
    if proxy_url:
        payload["proxy"] = {"url": proxy_url}

    try:
        response = requests.post(endpoint, json=payload, timeout=timeout_sec + 30)
        response.raise_for_status()
    except requests.RequestException as exc:
        raise SolveError(f"request to FlareSolverr failed: {exc}") from exc

    data = response.json()
    if data.get("status") != "ok":
        raise SolveError(f"FlareSolverr error: {data.get('message') or 'unknown'}")

    solution = data.get("solution") or {}
    cookies = solution.get("cookies") or []
    if not cookies:
        raise SolveError("FlareSolverr returned empty cookies")

    ua = str(solution.get("userAgent") or "")
    return {
        "cookies": cookie_string(cookies),
        "cookies_map": cookie_map(cookies),
        "cf_clearance": cookie_value(cookies, "cf_clearance"),
        "user_agent": ua,
        "browser": detect_browser(ua),
        "cookie_count": len(cookies),
    }
