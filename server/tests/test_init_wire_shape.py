"""Verify the init route wire shape matches the aw client contract."""

from aweb.routes.init import InitRequest, InitResponse


def test_init_request_accepts_aw_client_fields():
    """InitRequest must accept all fields the aw client sends."""
    req = InitRequest(
        project_slug="my-project",
        namespace_slug="example.com",
        alias="alice-01-agent",
        name="Alice",
        address_reachability="public",
        human_name="Alice Agent",
        agent_type="agent",
        did="did:key:z6Mktest",
        public_key="z6Mktest",
        custody="self",
        lifetime="persistent",
    )
    # namespace_slug should be normalized to namespace
    assert req.namespace == "example.com"


def test_init_request_accepts_namespace_directly():
    """InitRequest still accepts the namespace field directly."""
    req = InitRequest(
        project_slug="my-project",
        namespace="example.com",
    )
    assert req.namespace == "example.com"


def test_init_request_namespace_slug_does_not_override_namespace():
    """When both namespace and namespace_slug are provided, namespace wins."""
    req = InitRequest(
        project_slug="my-project",
        namespace="primary.com",
        namespace_slug="secondary.com",
    )
    assert req.namespace == "primary.com"


def test_init_request_accepts_coordination_extension_fields():
    """InitRequest accepts coordination fields alongside protocol fields."""
    req = InitRequest(
        project_slug="my-project",
        project_id="550e8400-e29b-41d4-a716-446655440000",
        repo_origin="https://github.com/test/repo.git",
        role="agent",
        hostname="dev-machine",
        workspace_path="/home/user/repo",
    )
    assert req.project_id == "550e8400-e29b-41d4-a716-446655440000"


def test_init_response_includes_identity_id():
    """InitResponse returns identity_id alongside agent_id for aw compat."""
    resp = InitResponse(
        created_at="2026-01-01T00:00:00Z",
        api_key="aw_sk_test",
        project_id="550e8400-e29b-41d4-a716-446655440000",
        project_slug="my-project",
        identity_id="660e8400-e29b-41d4-a716-446655440000",
        agent_id="660e8400-e29b-41d4-a716-446655440000",
        alias="alice-01-agent",
    )
    data = resp.model_dump()
    assert data["identity_id"] == data["agent_id"]
    assert "namespace_slug" in data
    assert "name" in data
    assert "server_url" in data
