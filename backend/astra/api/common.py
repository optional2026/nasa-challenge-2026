"""Shared route helpers: astronaut scoping and privacy filtering."""
from __future__ import annotations

from .. import db
from ..security import can_view_astronaut, can_view_private
from .framework import ApiError, Ctx, forbidden, not_found

API = None  # set in routes/__init__


def scoped_astronaut(ctx: Ctx, astronaut_id: str | None, required: bool = True) -> str | None:
    p = ctx.principal
    ast = astronaut_id or p.astronaut_id
    if ast is None:
        if required:
            raise ApiError(400, "astronaut_required", "astronaut_id query parameter is required for your role")
        return None
    if not db.one(ctx.conn, "SELECT id FROM astronauts WHERE id=?", (ast,)):
        raise not_found("astronaut", ast)
    if not can_view_astronaut(p, ast):
        raise forbidden("you may not view this astronaut's health data")
    return ast


def filter_private(ctx: Ctx, rows: list[dict], ast_key: str = "astronaut_id") -> tuple[list[dict], int]:
    out, hidden = [], 0
    for r in rows:
        if r.get("is_private") and not can_view_private(ctx.principal, r.get(ast_key)):
            hidden += 1
            continue
        out.append(r)
    return out, hidden


def default_mission(conn) -> dict:
    m = db.one(conn, "SELECT * FROM missions ORDER BY start_utc DESC LIMIT 1")
    if not m:
        raise ApiError(503, "not_seeded", "no mission configured")
    return m


def mission_day(m: dict) -> int:
    return int((db.utcnow() - db.parse_iso(m["start_utc"])).total_seconds() // 86400) + 1


def map_errors(fn):
    """Translate service exceptions into API errors."""
    def wrapper(ctx: Ctx):
        try:
            return fn(ctx)
        except ApiError:
            raise
        except LookupError as e:
            raise ApiError(404, "not_found", f"not found: {e}")
        except PermissionError as e:
            raise ApiError(403, "forbidden", str(e))
        except ValueError as e:
            details = getattr(e, "details", None)
            raise ApiError(422, "invalid", str(e), details)
    wrapper.__name__ = fn.__name__
    wrapper.__doc__ = fn.__doc__
    return wrapper
