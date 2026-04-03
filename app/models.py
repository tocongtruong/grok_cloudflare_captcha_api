from pydantic import BaseModel, Field
from typing import Any


class SolveRequest(BaseModel):
    sso_token: str = Field(min_length=1, description="SSO token, co the truyen dang sso=...")


class HeaderInfo(BaseModel):
    cookie: str
    cf_clearance: str
    userAgent: str


class NetworkInfo(BaseModel):
    proxy_mode: str
    url_proxy: str
    egress_ip: str
    egress_ip_source: str


class SolveResponse(BaseModel):
    status: str
    header: HeaderInfo
    network: NetworkInfo


class TokenRequest(BaseModel):
    sso_token: str = Field(min_length=1, description="SSO token, co the truyen dang sso=...")


class TokenResponse(BaseModel):
    status: str
    header: HeaderInfo
    network: NetworkInfo
    quota: dict[str, Any]
    token_expired: bool
    reason: str
    upstream_status: int
    is_cloudflare: bool


class ErrorResponse(BaseModel):
    detail: str
