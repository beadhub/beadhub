#!/usr/bin/env python3
"""
Seed script to populate the BeadHub dashboard with realistic test data.

Run after database reset to have good data for UI testing:
    uv run python scripts/seed_dashboard.py

Or with a custom base URL:
    uv run python scripts/seed_dashboard.py --base-url http://localhost:8000
"""

import argparse
import uuid

import httpx

# Test data configuration
PROJECTS = [
    {
        "project_slug": "beadhub-all",
        "repos": ["beadhub", "aweb", "docs"],
    },
    {
        "project_slug": "acme-corp",
        "repos": ["frontend", "backend", "shared-lib"],
    },
]

AGENTS = [
    {"name": "frontend-bot", "program": "claude-code", "model": "claude-sonnet-4-20250514"},
    {"name": "backend-bot", "program": "claude-code", "model": "claude-sonnet-4-20250514"},
    {"name": "reviewer-bot", "program": "custom-agent", "model": "claude-opus-4-20250514"},
    {"name": "docs-bot", "program": "claude-code", "model": "claude-haiku-4-20250514"},
]

MEMBERS = [
    "alice@example.com",
    "bob@example.com",
    "carol@example.com",
]

SAMPLE_ESCALATIONS = [
    {
        "subject": "Architecture decision needed",
        "situation": "I'm implementing the new caching layer and there are two approaches:\n\n1. Use Redis with TTL-based invalidation\n2. Use in-memory cache with pub/sub invalidation\n\nBoth have tradeoffs. Which approach should I use?",
        "options": ["Redis TTL", "In-memory pub/sub", "Hybrid approach"],
    },
    {
        "subject": "Database migration conflict",
        "situation": "Found a conflict between migration 003 and 004. Both try to add a column 'status' to the users table. Need guidance on how to resolve.",
        "options": ["Keep 003", "Keep 004", "Merge both"],
    },
    {
        "subject": "Test failure in CI",
        "situation": "The test_reservation_race test is flaky in CI but passes locally. I've tried adding retries but the issue persists. Should I:\n- Skip the test temporarily\n- Increase timeouts\n- Rewrite the test",
        "options": ["Skip temporarily", "Increase timeouts", "Rewrite test"],
    },
    {
        "subject": "Security concern in auth flow",
        "situation": "Noticed the current auth implementation doesn't validate JWT expiry properly. This could allow expired tokens to be used. Should I:\n- Fix immediately (breaking change)\n- Add deprecation warning first\n- Document as known issue",
        "options": ["Fix immediately", "Deprecation warning", "Document issue"],
    },
    {
        "subject": "Performance issue detected",
        "situation": "The /v1/status endpoint is 3x slower than expected. Profiling shows the issue is in the Redis SCAN operation. Need guidance on whether to:\n- Optimize SCAN with better patterns\n- Add pagination to the API\n- Cache the results",
        "options": None,
    },
]


def create_workspace(
    client: httpx.Client, project_id: str, repo_id: str, repo: str, agent: dict, member: str
) -> str:
    """Register a workspace and return its ID."""
    workspace_id = str(uuid.uuid4())

    response = client.post(
        "/v1/workspaces/register",
        json={
            "workspace_id": workspace_id,
            "project_id": project_id,
            "repo_id": repo_id,
            "alias": agent["name"],
            "human_name": member.split("@")[0].title(),
        },
    )
    response.raise_for_status()
    print(f"  Created workspace {workspace_id[:8]}... ({agent['name']} in {repo})")
    return workspace_id


def create_escalation(
    client: httpx.Client, workspace_id: str, alias: str, escalation: dict, responded: bool = False
):
    """Create an escalation, optionally responding to it."""
    response = client.post(
        "/v1/escalations",
        json={
            "workspace_id": workspace_id,
            "alias": alias,
            "subject": escalation["subject"],
            "situation": escalation["situation"],
            "options": escalation.get("options"),
            "expires_in_hours": 24,
        },
    )
    response.raise_for_status()
    data = response.json()
    escalation_id = data["escalation_id"]
    print(f"  Created escalation: {escalation['subject'][:40]}...")

    if responded:
        response = client.post(
            f"/v1/escalations/{escalation_id}/respond",
            json={
                "response": "Go with option 1. It's the safest approach for now.",
                "note": "Reviewed with the team",
            },
        )
        response.raise_for_status()
        print("    -> Responded to escalation")


def seed_data(base_url: str):
    """Seed the dashboard with test data."""
    print(f"\nSeeding BeadHub at {base_url}...")

    client = httpx.Client(base_url=base_url, timeout=30.0)

    # Check health first
    try:
        response = client.get("/health")
        response.raise_for_status()
        print("Server is healthy\n")
    except Exception as e:
        print(f"Error: Could not connect to server at {base_url}")
        print(f"  {e}")
        return

    workspaces = []

    # Create workspaces for each project/repo combination
    print("Creating workspaces...")
    workspace_idx = 0
    for project in PROJECTS:
        project_slug = project["project_slug"]
        project_resp = client.post("/v1/projects/ensure", json={"slug": project_slug})
        project_resp.raise_for_status()
        project_id = project_resp.json()["project_id"]

        for repo in project["repos"]:
            repo_resp = client.post(
                "/v1/repos/ensure",
                json={
                    "project_id": project_id,
                    "origin_url": f"git@github.com:seed/{repo}.git",
                },
            )
            repo_resp.raise_for_status()
            repo_id = repo_resp.json()["repo_id"]

            # Assign an agent and member to this workspace
            agent = AGENTS[workspace_idx % len(AGENTS)]
            member = MEMBERS[workspace_idx % len(MEMBERS)]

            workspace_id = create_workspace(client, project_id, repo_id, repo, agent, member)
            workspaces.append(
                {
                    "workspace_id": workspace_id,
                    "project_slug": project_slug,
                    "repo": repo,
                    "agent": agent,
                    "member": member,
                }
            )
            workspace_idx += 1

    print(f"\nCreated {len(workspaces)} workspaces\n")

    # Create escalations
    print("Creating escalations...")
    esc_idx = 0
    for ws in workspaces[:3]:  # First 3 workspaces get escalations
        # Each workspace gets 1-2 escalations
        num_escalations = (esc_idx % 2) + 1
        for _ in range(num_escalations):
            if esc_idx < len(SAMPLE_ESCALATIONS):
                escalation = SAMPLE_ESCALATIONS[esc_idx]
                # Make some responded (every other one)
                responded = esc_idx % 2 == 1
                create_escalation(
                    client, ws["workspace_id"], ws["agent"]["name"], escalation, responded
                )
                esc_idx += 1

    print("\nCreated escalations\n")

    # Summary
    print("=" * 50)
    print("SEED COMPLETE")
    print("=" * 50)
    print(f"  Workspaces: {len(workspaces)}")
    print(f"  Projects: {', '.join(p['project_slug'] for p in PROJECTS)}")
    print(f"  Escalations: {esc_idx}")
    print("\nDashboard URL: http://localhost:5173")


def main():
    parser = argparse.ArgumentParser(description="Seed BeadHub dashboard with test data")
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="Base URL of the BeadHub API (default: http://localhost:8000)",
    )
    args = parser.parse_args()

    seed_data(args.base_url)


if __name__ == "__main__":
    main()
