from functools import lru_cache
import socket
from urllib.parse import urlparse

from fastapi import Depends, FastAPI, Header, HTTPException, status

from app.config import Settings
from app.models import HeaderInfo, SolveRequest, SolveResponse, TokenRequest, TokenResponse
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
        "proxy_mode": "warp" if active_proxy == settings.warp_proxy_url and active_proxy else ("base_proxy" if active_proxy else "direct"),
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

    return SolveResponse(
        status="ok",
        header=build_auth_header_info(sso_token, solved),
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
        quota=result.get("quota") if isinstance(result.get("quota"), dict) else {},
        token_expired=bool(result.get("token_expired", False)),
        reason=str(result.get("reason") or "unknown"),
        upstream_status=int(result.get("upstream_status") or 0),
        is_cloudflare=bool(result.get("is_cloudflare", False)),
    )
