"""A small, explicit HTTP layer on top of Starlette.

Provides: Pydantic validation of bodies and query strings, authentication
(bearer session tokens and device API keys), role checks, consistent JSON
errors, and OpenAPI 3.1 generation from the same route registry.
(FastAPI could not be installed in the build environment — see DECISIONS D-001.)
"""
from __future__ import annotations

import inspect
import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable

from pydantic import BaseModel, ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response
from starlette.routing import Route

from .. import db, security
from ..security import Principal


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, details: Any = None):
        super().__init__(message)
        self.status, self.code, self.message, self.details = status, code, message, details


def not_found(what: str, ident: Any) -> ApiError:
    return ApiError(404, "not_found", f"{what} '{ident}' not found")


def forbidden(msg: str = "not permitted for your role") -> ApiError:
    return ApiError(403, "forbidden", msg)


@dataclass
class Ctx:
    request: Request
    principal: Principal
    conn: Any
    path: dict
    body: Any = None
    query: Any = None
    headers: dict = field(default_factory=dict)

    def require_roles(self, *roles: str) -> None:
        if self.principal.role not in roles and self.principal.kind != "system":
            raise forbidden(f"requires one of roles: {', '.join(roles)}")


@dataclass
class RouteSpec:
    method: str
    path: str
    handler: Callable[[Ctx], Any]
    summary: str
    tags: list[str]
    body: type[BaseModel] | None
    query: type[BaseModel] | None
    response: type[BaseModel] | None
    auth: str  # 'none' | 'user' | 'user_or_device'
    roles: tuple[str, ...] | None
    status_code: int
    description: str


def _authenticate(request: Request, conn, mode: str) -> Principal:
    if mode == "none":
        return Principal(kind="anonymous", name="anonymous", role="anonymous")
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        token = auth[7:].strip()
        try:
            claims = security.decode_token(token)
        except Exception:
            raise ApiError(401, "invalid_token", "session token is invalid or expired")
        user = db.one(conn, "SELECT * FROM users WHERE id=? AND active=1", (int(claims["sub"]),))
        if not user:
            raise ApiError(401, "invalid_token", "user no longer active")
        mission_id = None
        if user["astronaut_id"]:
            a = db.one(conn, "SELECT mission_id FROM astronauts WHERE id=?", (user["astronaut_id"],))
            mission_id = a["mission_id"] if a else None
        return Principal(kind="user", name=user["username"], role=user["role"], user_id=user["id"],
                         astronaut_id=user["astronaut_id"], mission_id=mission_id,
                         display_name=user["display_name"])
    dev_key = request.headers.get("x-device-key")
    if dev_key and mode == "user_or_device":
        from ..services.ingestion import device_principal
        try:
            return device_principal(conn, dev_key)
        except PermissionError:
            raise ApiError(401, "invalid_device_key", "device key not recognised")
    raise ApiError(401, "unauthenticated", "authentication required (Bearer token" +
                   (" or X-Device-Key" if mode == "user_or_device" else "") + ")")


def _error_response(e: ApiError) -> JSONResponse:
    body = {"error": {"code": e.code, "message": e.message}}
    if e.details is not None:
        body["error"]["details"] = e.details
    return JSONResponse(body, status_code=e.status)


def _serialize(result: Any) -> Any:
    if isinstance(result, BaseModel):
        return result.model_dump(mode="json")
    if isinstance(result, list):
        return [_serialize(r) for r in result]
    if isinstance(result, dict):
        return {k: _serialize(v) for k, v in result.items()}
    return result


class Api:
    def __init__(self, prefix: str):
        self.prefix = prefix
        self.specs: list[RouteSpec] = []

    def route(self, method: str, path: str, *, summary: str, tags: list[str], body=None, query=None,
              response=None, auth: str = "user", roles: tuple[str, ...] | None = None,
              status_code: int = 200):
        def deco(fn: Callable[[Ctx], Any]):
            self.specs.append(RouteSpec(method.upper(), path, fn, summary, tags, body, query, response,
                                        auth, roles, status_code, inspect.getdoc(fn) or ""))
            return fn
        return deco

    # -------------------------------------------------------------- starlette glue
    def _endpoint(self, spec: RouteSpec):
        async def endpoint(request: Request) -> Response:
            raw_body = None
            if spec.body is not None:
                try:
                    raw = await request.body()
                    raw_body = json.loads(raw or b"null")
                except json.JSONDecodeError as exc:
                    return _error_response(ApiError(400, "invalid_json", f"request body is not valid JSON: {exc}"))

            def run() -> Response:
                conn = db.connect()
                try:
                    principal = _authenticate(request, conn, spec.auth)
                    if spec.roles and principal.role not in spec.roles and principal.kind != "system":
                        raise forbidden(f"requires one of roles: {', '.join(spec.roles)}")
                    body = None
                    if spec.body is not None:
                        try:
                            body = spec.body.model_validate(raw_body)
                        except ValidationError as ve:
                            raise ApiError(422, "validation_error", "request body failed validation",
                                           json.loads(ve.json(include_url=False)))
                    query = None
                    if spec.query is not None:
                        qp: dict[str, Any] = {}
                        for k in request.query_params.keys():
                            vals = request.query_params.getlist(k)
                            qp[k] = vals if len(vals) > 1 else vals[0]
                        try:
                            query = spec.query.model_validate(qp)
                        except ValidationError as ve:
                            raise ApiError(422, "validation_error", "query parameters failed validation",
                                           json.loads(ve.json(include_url=False)))
                    ctx = Ctx(request=request, principal=principal, conn=conn,
                              path=dict(request.path_params), body=body, query=query,
                              headers={k.lower(): v for k, v in request.headers.items()})
                    result = spec.handler(ctx)
                    if isinstance(result, Response):
                        return result
                    return JSONResponse(_serialize(result), status_code=spec.status_code)
                except ApiError as e:
                    return _error_response(e)
                finally:
                    conn.close()

            return await run_in_threadpool(run)

        endpoint.__name__ = spec.handler.__name__
        return endpoint

    def starlette_routes(self) -> list[Route]:
        return [Route(self.prefix + s.path, self._endpoint(s), methods=[s.method]) for s in self.specs]

    # -------------------------------------------------------------- OpenAPI
    def openapi(self, title: str, version: str, description: str) -> dict:
        components: dict[str, Any] = {}

        def ref(model: type[BaseModel]) -> dict:
            schema = model.model_json_schema(ref_template="#/components/schemas/{model}")
            for name, sub in schema.pop("$defs", {}).items():
                components[name] = sub
            components[model.__name__] = schema
            return {"$ref": f"#/components/schemas/{model.__name__}"}

        paths: dict[str, Any] = {}
        for s in self.specs:
            oa_path = self.prefix + s.path
            params = []
            for name in re.findall(r"{(\w+)(?::\w+)?}", s.path):
                params.append({"name": name, "in": "path", "required": True, "schema": {"type": "string"}})
            oa_path = re.sub(r"{(\w+):\w+}", r"{\1}", oa_path)
            if s.query is not None:
                qs = s.query.model_json_schema()
                req = set(qs.get("required", []))
                for pname, pschema in qs.get("properties", {}).items():
                    params.append({"name": pname, "in": "query", "required": pname in req,
                                   "schema": {k: v for k, v in pschema.items() if k != "title"},
                                   "description": pschema.get("description", "")})
            op: dict[str, Any] = {"summary": s.summary, "tags": s.tags, "operationId": s.handler.__name__,
                                  "description": s.description, "parameters": params,
                                  "responses": {str(s.status_code): {"description": "Success"},
                                                "401": {"description": "Not authenticated"},
                                                "403": {"description": "Forbidden for role"},
                                                "422": {"description": "Validation error"}}}
            if s.response is not None:
                op["responses"][str(s.status_code)]["content"] = {"application/json": {"schema": ref(s.response)}}
            if s.body is not None:
                op["requestBody"] = {"required": True, "content": {"application/json": {"schema": ref(s.body)}}}
            if s.auth == "user":
                op["security"] = [{"bearerAuth": []}]
            elif s.auth == "user_or_device":
                op["security"] = [{"bearerAuth": []}, {"deviceKey": []}]
            if s.roles:
                op["x-roles"] = list(s.roles)
            paths.setdefault(oa_path, {})[s.method.lower()] = op
        return {
            "openapi": "3.1.0",
            "info": {"title": title, "version": version, "description": description},
            "paths": paths,
            "components": {"schemas": components, "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"},
                "deviceKey": {"type": "apiKey", "in": "header", "name": "X-Device-Key"}}},
        }
