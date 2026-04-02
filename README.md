# cf-cookie-api

FastAPI mini service de lay cookie Cloudflare tu FlareSolverr va sinh bo header toi thieu de ban goi tiep endpoint Grok.

## 1) Chay nhanh bang Docker

```bash
cd cf-cookie-api
cp .env.example .env
docker compose up -d --build
```

Service:
- API: http://localhost:8090
- Docs: http://localhost:8090/api/docs
- FlareSolverr: http://localhost:8191

## 2) Kiem tra health

```bash
curl "http://localhost:8090/health"
```

## 3) Bootstrap phien bang sso token (khuyen dung)

```bash
curl -X POST "http://localhost:8090/api/cloudflaresolver" \
  -H "Content-Type: application/json" \
  -d '{
    "sso_token": "your-sso-token"
  }'
```

Ket qua tra ve:
- status
- header.cookie
- header.cf_clearance
- header.userAgent

## 4) Tong hop thong tin token trong 1 endpoint

Endpoint nay goi truc tiep `https://grok.com/rest/rate-limits` ben trong server,
dong thoi tra ve ca quota va ket qua phan loai token het han/cloudflare.

```bash
curl -X POST "http://localhost:8090/api/token" \
  -H "Content-Type: application/json" \
  -d '{
    "sso_token": "your-sso-token"
  }'
```

Ket qua tra ve:
- status
- header.cookie
- header.cf_clearance
- header.userAgent
- quota (du lieu raw tu upstream, thuong co `remainingTokens` hoac `remainingQueries`)
- token_expired (true/false)
- reason (active, token_expired, cloudflare_blocked, auth_unknown, upstream_error)
- upstream_status
- is_cloudflare

## 5) Bao ve endpoint bang API key (khuyen nghi)

Dat trong `.env`:

```env
API_KEY=your-secret-key
```

Khi do can gui them 1 trong 2 header:
- x-api-key: your-secret-key
- Authorization: Bearer your-secret-key

## Bien moi truong

- FLARESOLVERR_URL: URL FlareSolverr API.
- TARGET_URL: URL mac dinh de solve Cloudflare.
- TIMEOUT_SEC: timeout khi solve (giay).
- BASE_PROXY_URL: proxy URL neu can giu on dinh exit IP.
- WARP_AUTO_PRIORITY: bat/tat uu tien Warp proxy (mac dinh true).
- WARP_PROXY_URL: dia chi Warp proxy (mac dinh socks5://warp:1080).
- API_KEY: bao ve API cua ban.

## 6) Warp proxy (tuy chon, de o trang thai comment)

- Trong file compose da co san block `warp` o dang comment.
- Khi can dung, chi viec bo `#` block do roi chay lai `docker compose up -d --build`.
- He thong se tu uu tien Warp neu Warp reachable.
- Neu Warp chua bat hoac khong reachable thi tu dong fallback ve `BASE_PROXY_URL`; neu `BASE_PROXY_URL` rong thi di truc tiep bang IP that.

## Ghi chu

- Cookie Cloudflare thuong gan voi IP, vi vay neu ban dung proxy thi nen giu dong nhat IP giua buoc solve va buoc goi endpoint.
- Flow toi gian: chi can truyen `sso_token`, server se tu dong gen `sso`, `sso-rw`, giai CF va tao bo header toi thieu.
- Du an nay la thu muc doc lap, khong chinh sua grok2api hoac cf-refresh-external.
