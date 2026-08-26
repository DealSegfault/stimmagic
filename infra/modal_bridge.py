"""Authenticated local HTTP/WebSocket bridge to the Modal ComfyUI endpoint."""

from __future__ import annotations

import asyncio
import os
from urllib.parse import urlsplit, urlunsplit

from aiohttp import ClientSession, ClientTimeout, WSMsgType, web


HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailers",
    "transfer-encoding",
    "upgrade",
}


def require_env(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


TARGET = require_env("COMFY_MODAL_URL").rstrip("/")
REPAINT_TARGET = os.environ.get("REPAINT_MODAL_URL", "").rstrip("/")
AUTH_HEADERS = {
    "Modal-Key": require_env("MODAL_PROXY_TOKEN_ID"),
    "Modal-Secret": require_env("MODAL_PROXY_TOKEN_SECRET"),
}
TIMEOUT = ClientTimeout(total=None, sock_connect=20 * 60, sock_read=None)


def target_url(request: web.Request, websocket: bool = False, base_target: str = TARGET, path_override: str | None = None) -> str:
    base = urlsplit(base_target)
    scheme = "wss" if websocket and base.scheme == "https" else base.scheme
    if websocket and base.scheme == "http":
        scheme = "ws"
    path = path_override if path_override is not None else request.rel_url.path
    return urlunsplit((scheme, base.netloc, path, request.rel_url.query_string, ""))


def request_headers(request: web.Request) -> dict[str, str]:
    headers = {
        name: value
        for name, value in request.headers.items()
        if name.lower() not in HOP_BY_HOP
        and name.lower() not in {"host", "content-length"}
        and not name.lower().startswith("sec-websocket-")
    }
    headers.update(AUTH_HEADERS)
    return headers


async def relay_ws(source, destination) -> None:
    async for message in source:
        if message.type == WSMsgType.TEXT:
            await destination.send_str(message.data)
        elif message.type == WSMsgType.BINARY:
            await destination.send_bytes(message.data)
        elif message.type == WSMsgType.PING:
            await destination.ping(message.data)
        elif message.type == WSMsgType.PONG:
            await destination.pong(message.data)
        elif message.type in {WSMsgType.CLOSE, WSMsgType.CLOSED, WSMsgType.ERROR}:
            break


async def websocket_proxy(request: web.Request) -> web.WebSocketResponse:
    local_ws = web.WebSocketResponse(compress=False, heartbeat=30, max_msg_size=0)
    await local_ws.prepare(request)

    session: ClientSession = request.app["session"]
    try:
        async with session.ws_connect(
            target_url(request, websocket=True),
            headers=request_headers(request),
            compress=0,
            heartbeat=30,
            max_msg_size=0,
        ) as remote_ws:
            local_to_remote = asyncio.create_task(relay_ws(local_ws, remote_ws))
            remote_to_local = asyncio.create_task(relay_ws(remote_ws, local_ws))
            done, pending = await asyncio.wait(
                {local_to_remote, remote_to_local},
                return_when=asyncio.FIRST_COMPLETED,
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*done, *pending, return_exceptions=True)
    finally:
        await local_ws.close()
    return local_ws


async def http_proxy(request: web.Request) -> web.StreamResponse:
    if request.headers.get("Upgrade", "").lower() == "websocket":
        return await websocket_proxy(request)

    session: ClientSession = request.app["session"]
    is_repaint = request.path == "/repaint" or request.path.startswith("/repaint/")
    if is_repaint and not REPAINT_TARGET:
        return web.json_response({"error": {"code": "repaint_not_configured", "message": "REPAINT_MODAL_URL is not configured on the Modal bridge."}}, status=503)
    base_target = REPAINT_TARGET if is_repaint else TARGET
    path_override = request.path[len("/repaint"):] if is_repaint else request.rel_url.path
    # Modal's HTTP proxy currently rejects a forwarded streaming body when the
    # bridge lets aiohttp select chunked transfer encoding (the remote error is
    # `chunked can not be set if "Transfer-Encoding: chunked" header is set`).
    # Buffer request bodies at this small authenticated bridge and send an
    # explicit length. Generation inputs are normally images/video/audio, and
    # this keeps the upload path deterministic while responses remain streamed.
    body = await request.read() if request.can_read_body else None
    upstream_headers = request_headers(request)
    if body is not None:
        upstream_headers["Content-Length"] = str(len(body))

    async with session.request(
        request.method,
        target_url(request, base_target=base_target, path_override=path_override),
        headers=upstream_headers,
        data=body,
        allow_redirects=False,
    ) as upstream:
        headers = {
            name: value
            for name, value in upstream.headers.items()
            if name.lower() not in HOP_BY_HOP and name.lower() != "content-length"
        }
        response = web.StreamResponse(status=upstream.status, headers=headers)
        await response.prepare(request)
        async for chunk in upstream.content.iter_chunked(1024 * 1024):
            await response.write(chunk)
        await response.write_eof()
        return response


async def session_context(app: web.Application):
    app["session"] = ClientSession(timeout=TIMEOUT, auto_decompress=False)
    yield
    await app["session"].close()


def main() -> None:
    app = web.Application(client_max_size=4 * 1024**3)
    app.cleanup_ctx.append(session_context)
    app.router.add_route("*", "/{path:.*}", http_proxy)
    port = int(os.environ.get("MODAL_BRIDGE_PORT", "8190"))
    web.run_app(app, host="127.0.0.1", port=port, print=None)


if __name__ == "__main__":
    main()
