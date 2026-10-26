from __future__ import annotations

import pathlib

import yaml
from starlette.routing import WebSocketRoute
from world_server.app import create_app

ROOT = pathlib.Path(__file__).resolve().parents[2]


def _spec() -> dict:
    return yaml.safe_load((ROOT / "docs/contracts/api.openapi.yaml").read_text(encoding="utf-8"))


def test_every_openapi_operation_is_implemented() -> None:
    spec = _spec()
    app = create_app()
    implemented: set[tuple[str, str]] = set()
    websocket_paths: set[str] = set()
    for route in app.routes:
        methods = getattr(route, "methods", None)
        if methods:
            for method in methods:
                if method not in {"HEAD", "OPTIONS"}:
                    implemented.add((route.path, method.upper()))
        elif isinstance(route, WebSocketRoute):
            websocket_paths.add(route.path)

    missing = [
        (path, method.upper())
        for path, operations in spec["paths"].items()
        for method in operations
        if (path, method.upper()) not in implemented
    ]
    assert not missing, missing

    missing_ws = [path for path in spec.get("x-websocket", {}) if path not in websocket_paths]
    assert not missing_ws, missing_ws


def test_implemented_routes_are_documented_or_internal() -> None:
    spec = _spec()
    documented = set(spec["paths"]) | set(spec.get("x-websocket", {}))
    internal = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}
    app = create_app()
    undocumented = [
        route.path
        for route in app.routes
        if route.path not in documented and route.path not in internal
    ]
    assert not undocumented, undocumented
