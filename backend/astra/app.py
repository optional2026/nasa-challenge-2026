"""ASTRA application: Starlette app with REST API, WebSocket real-time
channel, OpenAPI document, offline API docs page and the built frontend."""
from __future__ import annotations

import asyncio
import contextlib
import mimetypes
import os
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware
from starlette.responses import FileResponse, HTMLResponse, JSONResponse
from starlette.routing import Mount, Route, WebSocketRoute
from starlette.staticfiles import StaticFiles
from starlette.websockets import WebSocket, WebSocketDisconnect

from . import config, db, security, seed, sides
from .protection import ProtectionMiddleware
from .api import routes_data, routes_health, routes_ops, routes_replication
from .api.framework import Api
from .bus import BUS
from .security import Principal
from .services import replication, sync

VERSION = "1.1.0"
mimetypes.add_type("application/manifest+json", ".webmanifest")
mimetypes.add_type("text/javascript", ".js")
api = Api(config.API_PREFIX)
routes_data.register(api)
routes_health.register(api)
routes_ops.register(api)
routes_replication.register(api)

DESCRIPTION = ("ASTRA — Astronaut Self-assessment, Tracking and Response Assistant. Decision-support prototype for the "
               "NASA Space Apps Challenge 2026. Not an autonomous doctor. All demo data is SYNTHETIC; rules marked "
               "DEMONSTRATION_ONLY are not clinical thresholds.")


def openapi_doc() -> dict:
    return api.openapi("ASTRA API", VERSION, DESCRIPTION)


async def openapi_json(request):
    return JSONResponse(openapi_doc())


async def api_docs(request):
    """Offline API documentation page (no CDN)."""
    doc = openapi_doc()
    rows = []
    for path, ops in doc["paths"].items():
        for method, op in ops.items():
            auth = "none" if "security" not in op else ("bearer / device key" if len(op["security"]) > 1 else "bearer")
            roles = ", ".join(op.get("x-roles", [])) or "—"
            body = op.get("requestBody", {}).get("content", {}).get("application/json", {}).get("schema", {}).get("$ref", "")
            rows.append(f"<tr><td class=m-{method}>{method.upper()}</td><td><code>{path}</code></td><td>{op['summary']}</td>"
                        f"<td>{auth}</td><td>{roles}</td><td>{body.split('/')[-1]}</td></tr>")
    html = f"""<!doctype html><html><head><meta charset=utf-8><title>ASTRA API</title><style>
body{{font:14px system-ui;background:#0b1220;color:#dbe4f0;margin:2rem}}table{{border-collapse:collapse;width:100%}}
td,th{{border-bottom:1px solid #22314a;padding:6px;text-align:left}}code{{color:#8fd3ff}}.m-get{{color:#6ee7b7}}.m-post{{color:#fbbf24}}
a{{color:#8fd3ff}}</style></head><body><h1>ASTRA API v{VERSION}</h1><p>{DESCRIPTION}</p>
<p>Machine-readable OpenAPI 3.1: <a href="/api/openapi.json">/api/openapi.json</a> · WebSocket: <code>/ws?token=…</code></p>
<table><tr><th>Method</th><th>Path</th><th>Summary</th><th>Auth</th><th>Roles</th><th>Body schema</th></tr>{''.join(rows)}</table>
</body></html>"""
    return HTMLResponse(html)


async def websocket_endpoint(ws: WebSocket):
    token = ws.query_params.get("token")
    try:
        claims = security.decode_token(token or "")
    except Exception:
        await ws.close(code=4401)
        return
    with db.session() as conn:
        u = db.one(conn, "SELECT * FROM users WHERE id=? AND active=1", (int(claims["sub"]),))
        p = (security.user_principal(conn, u) if u and u["role"] == claims.get("role") and sides.role_allowed(u["role"])
             else None)
    if not p:
        await ws.close(code=4401)
        return
    await ws.accept()
    sub = BUS.subscribe(p, asyncio.get_running_loop())
    await ws.send_json({"type": "hello", "at": db.now_iso(), "payload": {"user": u["username"], "role": u["role"]}})

    async def sender():
        while True:
            msg = await sub.queue.get()
            await ws.send_json(msg)

    task = asyncio.create_task(sender())
    try:
        while True:
            msg = await ws.receive_text()
            if msg == "ping":
                await ws.send_json({"type": "pong", "at": db.now_iso()})
    except WebSocketDisconnect:
        pass
    finally:
        task.cancel()
        BUS.unsubscribe(sub)


def _frontend_routes() -> list:
    dist = config.FRONTEND_DIST
    if not (dist / "index.html").exists():
        async def no_frontend(request):
            return HTMLResponse("<h1>ASTRA backend running</h1><p>Frontend bundle not found. Build it with "
                                "<code>npm run build</code> in <code>frontend/</code>. API docs: <a href='/api/docs'>/api/docs</a></p>")
        return [Route("/", no_frontend)]

    async def spa(request):
        return FileResponse(dist / "index.html")
    routes = [Route("/", spa)]
    if (dist / "assets").exists():
        routes.append(Mount("/assets", app=StaticFiles(directory=dist / "assets"), name="assets"))
    for f in dist.iterdir():
        if f.is_file() and f.name != "index.html":
            headers = {"Cache-Control": "no-cache"} if f.suffix in (".js", ".webmanifest") else None
            routes.append(Route("/" + f.name, (lambda p, h: (lambda r: FileResponse(p, headers=h)))(f, headers)))
    routes.append(Route("/{path:path}", spa))
    return routes


@contextlib.asynccontextmanager
async def lifespan(app):
    with db.session() as conn:
        db.init_db(conn)
        info = seed.seed_all(conn)
        seed.apply_demo_password(conn)
    if info.get("seeded"):
        print(f"[astra] seeded synthetic demo dataset: {info}")
    dep = config.deployment()
    print(f"[astra] deployment: {sides.SIDE_LABEL[dep]} (node {config.node_id()})")
    worker = None
    if dep == "onboard":
        # Change capture is installed AFTER the pre-flight reference dataset exists (both sides are provisioned with
        # it), so only records created aboard from now on are queued for Earth.
        with db.session() as conn:
            replication.install_triggers(conn)
            if replication.get_state(conn, "simulated_outage") == "1":
                print("[astra] Earth link: SIMULATED OUTAGE is active (set by the CMO; persists across restarts)"
                      if config.allow_link_simulation() else
                      "[astra] stored simulated outage ignored: ASTRA_ALLOW_LINK_SIMULATION is not enabled")
        if not config.earth_url() or not config.sync_key():
            print("[astra] WARNING: ASTRA_EARTH_URL / ASTRA_SYNC_KEY not configured — records stay queued onboard")
    if os.environ.get("ASTRA_DISABLE_SYNC_WORKER") != "1":
        if dep == "onboard":
            worker = replication.SyncWorker()
            replication.WORKER = worker
        elif dep == "standalone":
            worker = sync.SyncWorker()  # legacy in-process simulated ground station
        if worker:
            worker.start()
    try:
        yield
    finally:
        if worker:
            worker.stop_event.set()
            if isinstance(worker, replication.SyncWorker):
                worker.wake.set()
                replication.WORKER = None
        from simulator.source import RUNNER
        RUNNER.stop()


async def public_config(request):
    """Tells the login page whether this is the public demo server (no secrets)."""
    dep = config.deployment()
    return JSONResponse({"public_demo": config.public_demo(), "show_demo_password": not config.public_demo(),
                         "data": "synthetic", "deployment": dep, "side_label": sides.SIDE_LABEL[dep],
                         "allowed_roles": list(sides.allowed_roles()), "node_id": config.node_id()})


async def api_not_found(request):
    return JSONResponse({"error": {"code": "not_found", "message": f"no API route {request.method} {request.url.path}"}}, status_code=404)


def create_app() -> Starlette:
    routes = api.starlette_routes() + [
        Route("/api/openapi.json", openapi_json),
        Route("/api/docs", api_docs),
        Route("/api/v1/public-config", public_config),
        Route("/api/v1/replication/batch", routes_replication.replication_batch, methods=["POST"]),
        Route("/api/v1/replication/downlink", routes_replication.replication_downlink, methods=["GET"]),
        WebSocketRoute("/ws", websocket_endpoint),
        Route("/api/{path:path}", api_not_found, methods=["GET", "POST", "PUT", "PATCH", "DELETE"]),
    ] + _frontend_routes()
    return Starlette(routes=routes, lifespan=lifespan, middleware=[Middleware(ProtectionMiddleware), Middleware(GZipMiddleware, minimum_size=1024)])


app = create_app()
