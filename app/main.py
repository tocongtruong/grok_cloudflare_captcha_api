from functools import lru_cache
import socket
from urllib.parse import quote, urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, status
import requests

from app.config import Settings
from app.models import HeaderInfo, NetworkInfo, SolveRequest, SolveResponse, TokenRequest, TokenResponse
from app.quota import QuotaError, inspect_token_upstream
from app.solver import SolveError, solve_cloudflare

app = FastAPI(title="CF Cookie API", version="1.0.0", docs_url="/api/docs")


@lru_cache
def get_settings() -> Settings:
    settings = Settings.from_env()
    if not settings.flaresolverr_url:
        raise RuntimeError("FLARESOLVERR_URL is required")
    return settings


def parse_cookie_header(raw: str) -> dict[str, str]:
    out: dict[str, str] = {}
    for part in raw.split(";"):
        piece = part.strip()
        if not piece or "=" not in piece:
            continue
        key, value = piece.split("=", 1)
        key = key.strip()
        if not key:
            continue
        out[key] = value.strip()
    return out


def join_cookie_map(mapped: dict[str, str]) -> str:
    return "; ".join(f"{k}={v}" for k, v in mapped.items())


def merge_cookie_headers(primary: str, secondary: str) -> str:
    merged = parse_cookie_header(primary)
    merged.update(parse_cookie_header(secondary))
    return join_cookie_map(merged)


def normalize_sso_token(raw: str) -> str:
    token = (raw or "").strip()
    if token.startswith("sso="):
        token = token[4:]
    return token.strip()


def build_sso_cookie_header(token: str) -> str:
    return f"sso={token}; sso-rw={token}"


def build_auth_header_info(sso_token: str, solved: dict) -> HeaderInfo:
    auth_cookie = build_sso_cookie_header(sso_token)
    cookie_header = merge_cookie_headers(auth_cookie, solved["cookies"])
    user_agent = solved.get("user_agent") or "Mozilla/5.0"
    return HeaderInfo(
        cookie=cookie_header,
        cf_clearance=solved.get("cf_clearance") or "",
        userAgent=user_agent,
    )


def is_proxy_reachable(proxy_url: str, timeout_sec: float = 1.0) -> bool:
    parsed = urlparse(proxy_url)
    host = parsed.hostname
    if not host:
        return False

    port = parsed.port
    if port is None:
        if parsed.scheme.startswith("socks"):
            port = 1080
        elif parsed.scheme == "https":
            port = 443
        else:
            port = 80

    try:
        with socket.create_connection((host, port), timeout=timeout_sec):
            return True
    except OSError:
        return False


def pick_proxy_url(settings: Settings) -> str:
    warp_proxy = (settings.warp_proxy_url or "").strip()
    base_proxy = (settings.base_proxy_url or "").strip()

    if settings.warp_auto_priority and warp_proxy and is_proxy_reachable(warp_proxy):
        return warp_proxy
    if base_proxy:
        return base_proxy
    return ""


def build_public_http_proxy_url(settings: Settings, public_ip: str) -> str:
    ip = (public_ip or "").strip()
    if not ip:
        return ""

    port = int(settings.auto_http_proxy_port)
    user = (settings.auto_http_proxy_user or "").strip()
    password = (settings.auto_http_proxy_password or "").strip()

    if user:
        encoded_user = quote(user, safe="")
        encoded_pass = quote(password, safe="")
        return f"http://{encoded_user}:{encoded_pass}@{ip}:{port}"

    return f"http://{ip}:{port}"


def proxy_mode(settings: Settings, active_proxy: str) -> str:
    if active_proxy and active_proxy == (settings.warp_proxy_url or "").strip():
        return "warp"
    if active_proxy:
        return "base_proxy"
    return "direct"


def detect_egress_ip(timeout_sec: int, proxy_url: str = "") -> tuple[str, str]:
    endpoints = (
        "https://api.ipify.org?format=text",
        "https://ifconfig.me/ip",
    )
    proxies = None
    if proxy_url:
        proxies = {"http": proxy_url, "https": proxy_url}

    for endpoint in endpoints:
        try:
            response = requests.get(endpoint, timeout=max(5, min(timeout_sec, 20)), proxies=proxies)
            if response.ok:
                ip = (response.text or "").strip()
                if ip:
                    return ip, endpoint
        except requests.RequestException:
            continue
    return "", ""


def build_network_info(settings: Settings, active_proxy: str) -> NetworkInfo:
    mode = proxy_mode(settings, active_proxy)
    ip, source = detect_egress_ip(settings.timeout_sec, active_proxy)

    # For cross-VPS clients, always prefer explicit public proxy URL.
    # If not provided, auto-build one from detected public IP and HTTP proxy credentials.
    display_proxy = (settings.public_proxy_url or "").strip()
    if not display_proxy and settings.auto_http_proxy_enabled and ip:
        display_proxy = build_public_http_proxy_url(settings, ip)
    if not display_proxy:
        display_proxy = active_proxy

    return NetworkInfo(
        proxy_mode=mode,
        url_proxy=display_proxy,
        egress_ip=ip,
        egress_ip_source=source,
    )


def require_api_key(
    x_api_key: str | None = Header(default=None, alias="x-api-key"),
    authorization: str | None = Header(default=None),
    settings: Settings = Depends(get_settings),
) -> None:
    if not settings.api_key:
        return

    bearer = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer = authorization[7:].strip()

    if x_api_key == settings.api_key or bearer == settings.api_key:
        return

    raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="invalid API key")


@app.get("/health")
def health(settings: Settings = Depends(get_settings)) -> dict:
    active_proxy = pick_proxy_url(settings)
    return {
        "ok": True,
        "flaresolverr_url": settings.flaresolverr_url,
        "target_url": settings.target_url,
        "proxy_mode": proxy_mode(settings, active_proxy),
    }


@app.post("/api/cloudflaresolver", response_model=SolveResponse, dependencies=[Depends(require_api_key)])
def solve_cf(payload: SolveRequest, settings: Settings = Depends(get_settings)) -> SolveResponse:
    target_url = settings.target_url.strip()
    proxy_url = pick_proxy_url(settings)
    sso_token = normalize_sso_token(payload.sso_token)

    if not sso_token:
        raise HTTPException(status_code=400, detail="sso_token is empty")

    try:
        solved = solve_cloudflare(
            flaresolverr_url=settings.flaresolverr_url,
            target_url=target_url,
            timeout_sec=settings.timeout_sec,
            proxy_url=proxy_url,
        )
    except SolveError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    network = build_network_info(settings, proxy_url)

    return SolveResponse(
        status="ok",
        header=build_auth_header_info(sso_token, solved),
        network=network,
    )


@app.post("/api/token", response_model=TokenResponse, dependencies=[Depends(require_api_key)])
def inspect_token(payload: TokenRequest, settings: Settings = Depends(get_settings)) -> TokenResponse:
    target_url = settings.target_url.strip()
    proxy_url = pick_proxy_url(settings)
    sso_token = normalize_sso_token(payload.sso_token)

    if not sso_token:
        raise HTTPException(status_code=400, detail="sso_token is empty")

    try:
        solved = solve_cloudflare(
            flaresolverr_url=settings.flaresolverr_url,
            target_url=target_url,
            timeout_sec=settings.timeout_sec,
            proxy_url=proxy_url,
        )
    except SolveError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    header = build_auth_header_info(sso_token, solved)
    network = build_network_info(settings, proxy_url)

    try:
        result = inspect_token_upstream(
            cookie_header=header.cookie,
            user_agent=header.userAgent,
            timeout_sec=settings.timeout_sec,
            proxy_url=proxy_url,
        )
    except QuotaError as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc

    return TokenResponse(
        status=str(result.get("status") or "ok"),
        header=header,
        network=network,
        quota=result.get("quota") if isinstance(result.get("quota"), dict) else {},
        token_expired=bool(result.get("token_expired", False)),
        reason=str(result.get("reason") or "unknown"),
        upstream_status=int(result.get("upstream_status") or 0),
        is_cloudflare=bool(result.get("is_cloudflare", False)),
    )
