import json
import os

import httpx
import typer
import uvicorn

from .config import get_settings
from .workspace_config import get_workspace_id

app = typer.Typer(help="BeadHub OSS Core CLI")


def _resolve_workspace_id(override: str | None) -> str:
    """Resolve workspace_id from override or .beadhub file.

    Args:
        override: Explicit workspace_id from --workspace-id flag.

    Returns:
        workspace_id string.

    Raises:
        typer.Exit: If no workspace_id is available.
    """
    workspace_id = get_workspace_id(override=override)
    if not workspace_id:
        typer.echo(
            "Error: No workspace_id available.\n"
            "Either:\n"
            "  - Run 'bdh :init' to create a .beadhub file\n"
            "  - Pass --workspace-id explicitly",
            err=True,
        )
        raise typer.Exit(1)
    return workspace_id


def _resolve_api_key(override: str | None) -> str | None:
    if override:
        return override
    return os.getenv("BEADHUB_API_KEY")


def _handle_api_call(
    method: str,
    url: str,
    allow_statuses: set[int] | None = None,
    api_key: str | None = None,
    **kwargs,
) -> httpx.Response:
    """
    Execute an HTTP request with proper error handling.
    Handles network errors, timeouts, and HTTP status errors gracefully.

    Args:
        method: HTTP method (GET, POST, DELETE)
        url: Request URL
        allow_statuses: Set of status codes to allow through (e.g., {404, 409})
        api_key: API key to include as Authorization: Bearer header
        **kwargs: Additional arguments passed to httpx
    """
    # Build headers with Authorization if provided (or from BEADHUB_API_KEY env var).
    headers = kwargs.pop("headers", {})
    api_key = api_key or os.getenv("BEADHUB_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        if method == "GET":
            resp = httpx.get(url, timeout=30, headers=headers, **kwargs)
        elif method == "POST":
            resp = httpx.post(url, timeout=30, headers=headers, **kwargs)
        elif method == "DELETE":
            resp = httpx.delete(url, timeout=30, headers=headers, **kwargs)
        else:
            raise ValueError(f"Unsupported method: {method}")

        # Allow specific status codes through for caller handling
        if allow_statuses and resp.status_code in allow_statuses:
            return resp

        # Handle common HTTP errors with friendly messages
        if resp.status_code == 401:
            typer.echo("Error: Unauthorized - API key required", err=True)
            raise typer.Exit(1)
        elif resp.status_code == 403:
            typer.echo("Error: Forbidden - insufficient permissions", err=True)
            raise typer.Exit(1)
        elif resp.status_code >= 500:
            typer.echo(f"Error: Server error ({resp.status_code})", err=True)
            raise typer.Exit(1)

        return resp

    except httpx.ConnectError:
        api_base = _get_api_base()
        typer.echo(f"Error: Cannot connect to BeadHub API at {api_base}", err=True)
        typer.echo("Is the server running? Try: beadhub serve", err=True)
        raise typer.Exit(1)
    except httpx.TimeoutException:
        typer.echo("Error: Request timed out", err=True)
        raise typer.Exit(1)
    except httpx.RequestError as e:
        typer.echo(f"Error: Network error - {e}", err=True)
        raise typer.Exit(1)


escalations_app = typer.Typer(help="Manage escalations")
beads_app = typer.Typer(help="Beads integration")
app.add_typer(escalations_app, name="escalations")
app.add_typer(beads_app, name="beads")


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Host interface to bind"),
    port: int | None = typer.Option(None, help="Port to bind"),
    reload: bool | None = typer.Option(None, help="Enable auto-reload (development only)"),
    log_level: str | None = typer.Option(None, help="Log level for the server"),
) -> None:
    """
    Start the BeadHub API server.
    """
    settings = get_settings()

    uvicorn.run(
        "beadhub.api:create_app",
        host=host or settings.host,
        port=port or settings.port,
        reload=reload if reload is not None else settings.reload,
        log_level=log_level or settings.log_level,
        factory=True,
    )


@app.command()
def status(
    workspace_id: str | None = typer.Option(
        None, "--workspace-id", help="Workspace ID (reads from .beadhub if not provided)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """
    Show BeadHub workspace status (agent presence and escalations).
    """
    resolved_workspace_id = _resolve_workspace_id(workspace_id)
    params = {"workspace_id": resolved_workspace_id}
    resp = _handle_api_call("GET", f"{_get_api_base()}/v1/status", params=params)
    data = resp.json()

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    workspace = data.get("workspace", {})
    typer.echo(f"Workspace: {workspace.get('workspace_id')}")
    typer.echo(f"Timestamp: {data.get('timestamp')}")
    typer.echo("")

    agents = data.get("agents", [])
    if agents:
        typer.echo("Agents:")
        for agent in agents:
            typer.echo(
                f"  {agent.get('alias', '?'):15} status={agent.get('status', '?'):8} "
                f"issue={agent.get('current_issue') or '-'}"
            )
    else:
        typer.echo("Agents: (none)")

    typer.echo("")
    typer.echo(f"Escalations pending: {data.get('escalations_pending', 0)}")


def _get_api_base() -> str:
    return os.getenv("BEADHUB_API_URL", "http://localhost:8000")


@escalations_app.command("list")
def escalations_list(
    workspace_id: str | None = typer.Option(
        None, "--workspace-id", help="Workspace ID (reads from .beadhub if not provided)"
    ),
    status: str | None = typer.Option(None, help="Filter by status"),
    agent: str | None = typer.Option(None, help="Filter by agent name"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """
    List escalations from the API.
    """
    resolved_workspace_id = _resolve_workspace_id(workspace_id)
    params: dict[str, str] = {"workspace_id": resolved_workspace_id}
    if status:
        params["status"] = status
    if agent:
        params["alias"] = agent

    resp = _handle_api_call("GET", f"{_get_api_base()}/v1/escalations", params=params)
    data = resp.json()

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    for esc in data.get("escalations", []):
        typer.echo(
            f"{esc['escalation_id']}  {esc['status']:9}  {esc['alias']:15}  {esc['subject']}"
        )


@escalations_app.command("view")
def escalations_view(escalation_id: str) -> None:
    """
    View escalation details.
    """
    resp = _handle_api_call(
        "GET", f"{_get_api_base()}/v1/escalations/{escalation_id}", allow_statuses={404}
    )
    if resp.status_code == 404:
        typer.echo("Error: Escalation not found", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(resp.json(), indent=2))


@beads_app.command("issues")
def beads_issues(
    workspace_id: str | None = typer.Option(
        None, "--workspace-id", help="Workspace ID (reads from .beadhub if not provided)"
    ),
    api_key: str | None = typer.Option(
        None, "--api-key", help="BeadHub API key (defaults to BEADHUB_API_KEY)"
    ),
    status: str | None = typer.Option(None, help="Filter by status"),
    assignee: str | None = typer.Option(None, help="Filter by assignee"),
    label: str | None = typer.Option(None, help="Filter by label"),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """
    List Beads issues from BeadHub.
    """
    resolved_workspace_id = _resolve_workspace_id(workspace_id)
    resolved_api_key = _resolve_api_key(api_key)
    if not resolved_api_key:
        typer.echo("Error: BEADHUB_API_KEY not set (run `bdh :init` or pass --api-key)", err=True)
        raise typer.Exit(1)
    params: dict[str, str] = {"workspace_id": resolved_workspace_id}
    if status:
        params["status"] = status
    if assignee:
        params["assignee"] = assignee
    if label:
        params["label"] = label

    resp = _handle_api_call(
        "GET",
        f"{_get_api_base()}/v1/beads/issues",
        params=params,
        api_key=resolved_api_key,
    )
    data = resp.json()

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    for issue in data.get("issues", []):
        typer.echo(
            f"{issue['bead_id']}  P{issue['priority']}  {issue['status']:10}  {issue['title']}"
        )


@beads_app.command("ready")
def beads_ready(
    workspace_id: str | None = typer.Option(
        None, "--workspace-id", help="Workspace ID (reads from .beadhub if not provided)"
    ),
    api_key: str | None = typer.Option(
        None, "--api-key", help="BeadHub API key (defaults to BEADHUB_API_KEY)"
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON"),
) -> None:
    """
    Show Beads issues that are ready to work on.
    """
    resolved_workspace_id = _resolve_workspace_id(workspace_id)
    resolved_api_key = _resolve_api_key(api_key)
    if not resolved_api_key:
        typer.echo("Error: BEADHUB_API_KEY not set (run `bdh :init` or pass --api-key)", err=True)
        raise typer.Exit(1)
    params = {"workspace_id": resolved_workspace_id}
    resp = _handle_api_call(
        "GET",
        f"{_get_api_base()}/v1/beads/ready",
        params=params,
        api_key=resolved_api_key,
    )
    data = resp.json()

    if json_output:
        typer.echo(json.dumps(data, indent=2))
        return

    for issue in data.get("issues", []):
        typer.echo(f"{issue['bead_id']}  P{issue['priority']}  {issue['title']}")


@escalations_app.command("respond")
def escalations_respond(
    escalation_id: str,
    choice: str = typer.Option(..., "--choice", help="Chosen response"),
    note: str | None = typer.Option(None, "--note", help="Optional note"),
) -> None:
    """
    Respond to an escalation.
    """
    payload = {"response": choice}
    if note:
        payload["note"] = note

    resp = _handle_api_call(
        "POST",
        f"{_get_api_base()}/v1/escalations/{escalation_id}/respond",
        allow_statuses={404},
        json=payload,
    )
    if resp.status_code == 404:
        typer.echo("Error: Escalation not found", err=True)
        raise typer.Exit(1)
    typer.echo(json.dumps(resp.json(), indent=2))
