"""Routes: Earth-link status, CMO link-simulation control, replication status, ground follow-up notes, and the
server-to-server replication endpoints (signed; not usable with a user session)."""
from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from .. import audit, config, db
from ..bus import BUS
from ..security import can_view_astronaut
from ..services import replication
from .common import default_mission, scoped_astronaut
from .framework import Api, ApiError, Ctx, forbidden

CREW = ("astronaut", "medical_officer")
EARTH = ("admin", "flight_surgeon")


class AnnotationIn(BaseModel):
    astronaut_id: str = Field(min_length=1, max_length=64)
    kind: Literal["follow_up", "note", "request"] = "follow_up"
    text: str = Field(min_length=1, max_length=4000)
    subject_type: Literal["observation", "alert", "medical_event", "medical_report", "assessment"] | None = None
    subject_id: str | None = Field(default=None, max_length=128)


def _crew_scope(ctx: Ctx) -> set[str] | None:
    p = ctx.principal
    if p.role == "medical_officer":
        return set(p.crew_astronaut_ids) | ({p.astronaut_id} if p.astronaut_id else set())
    if p.role == "astronaut":
        return {p.astronaut_id} if p.astronaut_id else set()
    return set(p.scope_astronaut_ids) if p.scope_astronaut_ids is not None else None


def register(api: Api) -> None:
    @api.route("GET", "/link", summary="Earth-link and synchronization status of this server", tags=["sync"],
               roles=CREW + EARTH)
    def link(ctx: Ctx):
        """Onboard: Earth link state (available / unavailable — simulated / unreachable), outbound queue counts and
        the last successful synchronization. Earth: what has been received from the spacecraft and when."""
        if config.deployment() == "earth":
            return replication.earth_status(ctx.conn, _crew_scope(ctx))
        return replication.link_status(ctx.conn)

    def _sim_guard(ctx: Ctx) -> None:
        if config.deployment() != "onboard":
            raise ApiError(409, "not_onboard", "the Earth-link simulation exists only on the onboard (Crew Side) server")
        if not config.allow_link_simulation():
            raise ApiError(403, "simulation_disabled", "the Earth-link demonstration control is disabled on this deployment "
                                                       "(enable only in an authorised test environment: ASTRA_ALLOW_LINK_SIMULATION=1)")

    @api.route("POST", "/link/simulation/outage", summary="DEMONSTRATION: simulate loss of the Earth link (CMO only)",
               tags=["sync"], roles=("medical_officer",))
    def link_outage(ctx: Ctx):
        """Blocks the onboard synchronization transport (no record is delivered to Earth) until restored. The onboard
        server, the spacecraft network and every crew session keep working; no record is changed. Persistent across
        page reloads, new sessions and server restarts. Audited."""
        _sim_guard(ctx)
        return replication.set_simulated_outage(ctx.conn, ctx.principal, True)

    @api.route("POST", "/link/simulation/restore", summary="DEMONSTRATION: restore the Earth link (CMO only)", tags=["sync"],
               roles=("medical_officer",))
    def link_restore(ctx: Ctx):
        """Lifts the simulated outage; the synchronization service immediately transmits every pending record."""
        _sim_guard(ctx)
        return replication.set_simulated_outage(ctx.conn, ctx.principal, False)

    @api.route("GET", "/replication/unsynced", summary="Crew records not yet acknowledged by Earth (onboard)", tags=["sync"],
               roles=CREW)
    def unsynced(ctx: Ctx):
        """CMO: records of the astronauts in their crew; astronaut: own records only. Private items show only their
        type to anyone but the astronaut."""
        if config.deployment() != "onboard":
            raise ApiError(409, "not_onboard", "available on the onboard server only")
        p = ctx.principal
        rows = replication.unsynced_records(ctx.conn, _crew_scope(ctx))
        names = {a["id"]: a["name"] for a in db.all_(ctx.conn, "SELECT id, name FROM astronauts")}
        for r in rows:
            r["astronaut_name"] = names.get(r["astronaut_id"])
            if r["is_private"] and r["astronaut_id"] != p.astronaut_id:
                r["metric_code"] = None
                r["record_id"] = "[private]"
        return {"items": rows, "status": replication.link_status(ctx.conn)}

    @api.route("POST", "/replication/run", summary="Run one synchronization pass now (onboard; respects the link)",
               tags=["sync"], roles=("medical_officer",))
    def replication_run(ctx: Ctx):
        if config.deployment() != "onboard":
            raise ApiError(409, "not_onboard", "available on the onboard server only")
        return {"result": replication.run_pass(ctx.conn), "status": replication.link_status(ctx.conn)}

    # ---------------------------------------------------------------- ground follow-up notes
    @api.route("GET", "/ground/annotations", summary="Ground follow-up notes (Earth → crew)", tags=["sync"],
               roles=CREW + EARTH)
    def annotations(ctx: Ctx):
        ast = ctx.request.query_params.get("astronaut_id")
        scope = _crew_scope(ctx)
        sql, params = "SELECT * FROM ground_annotations", []
        if ast:
            scoped_astronaut(ctx, ast)
            sql += " WHERE astronaut_id=?"
            params.append(ast)
        rows = db.all_(ctx.conn, sql + " ORDER BY created_at DESC LIMIT 200", params)
        rows = [r for r in rows if r["astronaut_id"] is None or scope is None or r["astronaut_id"] in scope]
        names = {a["id"]: a["name"] for a in db.all_(ctx.conn, "SELECT id, name FROM astronauts")}
        for r in rows:
            r["astronaut_name"] = names.get(r["astronaut_id"])
        return {"side": config.deployment(), "items": rows}

    @api.route("POST", "/ground/annotations", summary="Add a ground follow-up note for the crew (Earth flight surgeon)",
               tags=["sync"], body=AnnotationIn, roles=("flight_surgeon",), status_code=201)
    def annotation_create(ctx: Ctx):
        """A separate, attributable record — the onboard observations themselves are never edited from Earth. Delivered
        to the onboard server (CMO) by the synchronization service when the link is available."""
        if config.deployment() != "earth":
            raise ApiError(409, "earth_only", "ground follow-up notes are written on the Earth Side server")
        b, p = ctx.body, ctx.principal
        a = db.one(ctx.conn, "SELECT id, mission_id FROM astronauts WHERE id=?", (b.astronaut_id,))
        if not a:
            raise ApiError(404, "not_found", f"astronaut '{b.astronaut_id}' not found")
        if not can_view_astronaut(p, b.astronaut_id):
            raise forbidden("this astronaut is not on your assigned mission")
        aid = db.new_id("GN")
        with db.transaction(ctx.conn):
            db.insert(ctx.conn, "ground_annotations", {
                "id": aid, "mission_id": a["mission_id"], "astronaut_id": b.astronaut_id, "subject_type": b.subject_type,
                "subject_id": b.subject_id, "kind": b.kind, "text": b.text, "author": p.actor,
                "author_role": p.role, "created_at": db.now_iso(), "delivered_at": None, "received_onboard_at": None})
            audit.record(ctx.conn, p, "ground_annotation.create", "ground_annotation", aid, {"astronaut_id": b.astronaut_id})
        BUS.publish("ground_annotation.created", {"id": aid}, astronaut_id=b.astronaut_id)
        return db.one(ctx.conn, "SELECT * FROM ground_annotations WHERE id=?", (aid,))


# ---------------------------------------------------------------- server-to-server (Earth side), signed
def _peer_error(status: int, code: str, msg: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": msg}}, status_code=status)


async def replication_batch(request: Request):
    if config.deployment() != "earth":
        return _peer_error(404, "not_found", "replication receiver is not enabled on this server")
    body = await request.body()
    if len(body) > 20 * 1024 * 1024:
        return _peer_error(413, "too_large", "batch too large")
    headers = {k.lower(): v for k, v in request.headers.items()}

    def run():
        conn = db.connect()
        try:
            try:
                node = replication.verify_request("POST", request.url.path, headers, body)
            except PermissionError as e:
                with db.transaction(conn):
                    audit.record(conn, f"peer:{headers.get('x-astra-node', '?')}", "replication.auth_rejected",
                                 "replication_batch", None, {"reason": str(e), "client": request.client.host if request.client else None})
                return _peer_error(401, "peer_authentication_failed", str(e))
            try:
                batch = json.loads(body or b"null")
                if not isinstance(batch, dict):
                    raise ValueError("batch must be a JSON object")
                return JSONResponse(replication.receive_batch(conn, node, batch))
            except (ValueError, replication.BatchError) as e:
                with db.transaction(conn):
                    audit.record(conn, f"peer:{node}", "replication.batch_rejected", "replication_batch", None, {"reason": str(e)})
                return _peer_error(400, "invalid_batch", str(e))
        finally:
            conn.close()
    return await run_in_threadpool(run)


async def replication_downlink(request: Request):
    if config.deployment() != "earth":
        return _peer_error(404, "not_found", "replication receiver is not enabled on this server")
    headers = {k.lower(): v for k, v in request.headers.items()}
    path = request.url.path + (("?" + request.url.query) if request.url.query else "")

    def run():
        conn = db.connect()
        try:
            try:
                node = replication.verify_request("GET", path, headers, b"")
            except PermissionError as e:
                return _peer_error(401, "peer_authentication_failed", str(e))
            try:
                after = int(request.query_params.get("after", "0"))
            except ValueError:
                return _peer_error(400, "invalid", "after must be an integer")
            return JSONResponse(replication.downlink(conn, node, after))
        finally:
            conn.close()
    return await run_in_threadpool(run)
