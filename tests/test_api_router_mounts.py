from fastapi.routing import APIRoute

from beadhub.api import create_app


def _first_route(app, path: str, method: str) -> APIRoute:
    for route in app.router.routes:
        if isinstance(route, APIRoute) and route.path == path and method in route.methods:
            return route
    raise AssertionError(f"Missing route for {method} {path}")


def test_create_app_mounts_aweb_routes_and_preserves_beadhub_overrides():
    app = create_app(serve_frontend=False)

    assert _first_route(app, "/v1/init", "POST").endpoint.__module__ == "beadhub.routes.init"
    assert _first_route(app, "/v1/agents", "GET").endpoint.__module__ == "beadhub.routes.agents"
    assert _first_route(app, "/v1/claims", "GET").endpoint.__module__ == "beadhub.routes.claims"
    assert _first_route(app, "/v1/policies", "POST").endpoint.__module__ == "beadhub.routes.policies"
    assert _first_route(app, "/v1/status", "GET").endpoint.__module__ == "beadhub.routes.status"
    assert _first_route(app, "/v1/tasks", "GET").endpoint.__module__ == "beadhub.routes.tasks"

    assert _first_route(app, "/v1/contacts", "GET").endpoint.__module__ == "aweb.routes.contacts"
    assert (
        _first_route(app, "/v1/conversations", "GET").endpoint.__module__
        == "aweb.routes.conversations"
    )
    assert _first_route(app, "/v1/events/stream", "GET").endpoint.__module__ == "aweb.routes.events"
