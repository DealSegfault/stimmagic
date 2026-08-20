"""Proxy to a tool provider's management UI (STP `presentation.management_url`).

The app renders a provider's manager inside a popover iframe. Loading it
straight from the provider host would be mixed content (http:// on a LAN /
tailnet box inside a secure-context window) and would need the user to hold
the provider's auth token; going through the local backend keeps a localhost
origin, forwards the STP token, and stamps X-Stimma-Manage so the provider
can tell app-originated mutations from random LAN traffic.

Profile-agnostic: providers are process-global.
"""

from typing import Optional

import httpx
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse

from core.logging import get_logger

log = get_logger(__name__)

router = APIRouter(prefix="/api/provider-manage", tags=["provider-manage"])

# Headers we never forward either direction
_HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "te", "trailer",
        "transfer-encoding", "upgrade", "host", "content-length", "cookie", "set-cookie",
        "x-profile-id", "x-profile-pin"}

_client: Optional[httpx.AsyncClient] = None


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None or _client.is_closed:
        _client = httpx.AsyncClient(timeout=httpx.Timeout(30.0, read=120.0), follow_redirects=False)
    return _client


def _resolve_target(provider_id: str, path: str, query: str) -> tuple:
    from providers import ProviderRegistry
    registry = ProviderRegistry.get_instance()
    provider = registry.get_provider(provider_id) if hasattr(registry, "get_provider") else registry._providers.get(provider_id)
    if provider is None:
        raise HTTPException(status_code=404, detail="Provider not found")
    base = getattr(provider, "management_url", None)
    if not base:
        raise HTTPException(status_code=404, detail="Provider has no management UI")
    base = base.rstrip("/") + "/"
    url = base + path.lstrip("/")
    if query:
        url += "?" + query
    headers = dict(getattr(provider, "management_auth_headers", {}) or {})
    return url, headers


@router.api_route("/{provider_id}", methods=["GET"])
async def manage_root_redirect(provider_id: str):
    # Ensure a trailing slash so relative asset paths inside the UI resolve
    return Response(status_code=307, headers={"Location": f"/api/provider-manage/{provider_id}/"})


@router.api_route("/{provider_id}/{path:path}", methods=["GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS"])
async def manage_proxy(provider_id: str, path: str, request: Request):
    url, extra_headers = _resolve_target(provider_id, path, request.url.query)
    headers = {k: v for k, v in request.headers.items() if k.lower() not in _HOP}
    headers.update(extra_headers)
    headers["X-Stimma-Manage"] = "1"
    headers.pop("origin", None)
    headers.pop("referer", None)
    body = await request.body()
    client = _get_client()
    try:
        upstream = await client.request(request.method, url, headers=headers, content=body if body else None)
    except httpx.HTTPError as e:
        log.warning("provider manage proxy failed", provider=provider_id, url=url, error=str(e))
        raise HTTPException(status_code=502, detail=f"Provider manager unreachable: {e}")
    resp_headers = {k: v for k, v in upstream.headers.items() if k.lower() not in _HOP and k.lower() not in ("content-encoding",)}
    # Rewrite upstream redirects that point back into the manager
    loc = upstream.headers.get("location")
    if loc and loc.startswith("/stp-v1/manage"):
        resp_headers["location"] = f"/api/provider-manage/{provider_id}/" + loc[len("/stp-v1/manage"):].lstrip("/")
    resp_headers.pop("x-frame-options", None)
    resp_headers.pop("content-security-policy", None)
    return Response(content=upstream.content, status_code=upstream.status_code, headers=resp_headers,
                    media_type=upstream.headers.get("content-type"))
