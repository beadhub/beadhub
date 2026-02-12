-- 001_initial.sql
-- Description: Baseline BeadHub server schema (clean-slate split)
--
-- Coordination primitives (mail/chat/locks/auth keys) live in `aweb`.
-- BeadHub owns: repos, workspaces, beads, claims, subscriptions, policies, escalations.

CREATE EXTENSION IF NOT EXISTS pgcrypto;

CREATE TABLE IF NOT EXISTS {{tables.projects}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Partition key for multi-tenant SaaS (NULL for single-tenant OSS mode)
    tenant_id UUID,
    slug TEXT NOT NULL,
    name TEXT,
    -- Active policy pointer (FK added after project_policies exists)
    active_policy_id UUID,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    -- Soft-delete support: NULL means active
    deleted_at TIMESTAMPTZ
);

-- Slugs unique within tenant (or globally if no tenant), for non-deleted projects.
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug_no_tenant
    ON {{tables.projects}}(slug) WHERE tenant_id IS NULL AND deleted_at IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug_with_tenant
    ON {{tables.projects}}(tenant_id, slug) WHERE tenant_id IS NOT NULL AND deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_projects_active ON {{tables.projects}}(id) WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS {{tables.repos}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- CASCADE: repos are deleted when their project is deleted (repos without projects are invalid)
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    origin_url TEXT NOT NULL,
    canonical_origin TEXT NOT NULL,
    name TEXT NOT NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    -- Soft-delete support: NULL means active, timestamp means deleted
    -- Unique constraint retained for ON CONFLICT support in ensure_repo.
    -- When a soft-deleted repo is re-registered, ensure_repo clears deleted_at.
    deleted_at TIMESTAMPTZ,
    CONSTRAINT unique_repo_per_project UNIQUE (project_id, canonical_origin)
);

CREATE INDEX IF NOT EXISTS idx_repos_project ON {{tables.repos}}(project_id);
CREATE INDEX IF NOT EXISTS idx_repos_active ON {{tables.repos}}(project_id)
    WHERE deleted_at IS NULL;

CREATE TABLE IF NOT EXISTS {{tables.workspaces}} (
    workspace_id UUID PRIMARY KEY,
    -- CASCADE: workspaces are deleted when their project is deleted
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    -- SET NULL: when repo is hard-deleted (e.g., project deletion cascade), preserve workspace for audit
    -- When repo is soft-deleted via API, workspaces are soft-deleted manually in application code
    repo_id UUID REFERENCES {{tables.repos}}(id) ON DELETE SET NULL,
    alias TEXT NOT NULL,
    human_name TEXT NOT NULL DEFAULT '',
    role TEXT,
    current_branch TEXT,
    focus_apex_bead_id TEXT,
    focus_apex_repo_name TEXT,
    focus_apex_branch TEXT,
    focus_updated_at TIMESTAMPTZ,
    -- Physical location: for detecting "gone" workspaces (directory no longer exists)
    -- Only checked for workspaces on the current hostname to avoid cross-machine false positives
    hostname TEXT,
    workspace_path TEXT,
    -- Workspace classification
    workspace_type TEXT NOT NULL DEFAULT 'agent',
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    -- Soft-delete support: NULL means active, timestamp means deleted
    deleted_at TIMESTAMPTZ,
    -- Track when workspace was last seen (updated on every bdh command)
    last_seen_at TIMESTAMPTZ,
    CONSTRAINT chk_workspace_repo CHECK (
        (workspace_type = 'agent' AND repo_id IS NOT NULL) OR
        (workspace_type IN ('dashboard') AND repo_id IS NULL)
    ),
    CONSTRAINT chk_workspace_role_length CHECK (role IS NULL OR length(role) <= 50)
);

-- Partial unique index: aliases unique within project for non-deleted workspaces only
CREATE UNIQUE INDEX IF NOT EXISTS idx_unique_active_alias
    ON {{tables.workspaces}}(project_id, alias)
    WHERE deleted_at IS NULL;

CREATE INDEX IF NOT EXISTS idx_workspaces_alias ON {{tables.workspaces}}(alias);
CREATE INDEX IF NOT EXISTS idx_workspaces_project ON {{tables.workspaces}}(project_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_repo ON {{tables.workspaces}}(repo_id);
CREATE INDEX IF NOT EXISTS idx_workspaces_active ON {{tables.workspaces}}(project_id)
    WHERE deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_workspaces_hostname ON {{tables.workspaces}}(hostname)
    WHERE hostname IS NOT NULL AND deleted_at IS NULL;
CREATE INDEX IF NOT EXISTS idx_workspaces_dashboard
    ON {{tables.workspaces}}(project_id, human_name)
    WHERE workspace_type = 'dashboard';

-- Trigger to update updated_at and enforce immutability
CREATE OR REPLACE FUNCTION {{schema}}.update_workspace_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    -- Enforce immutability of key fields
    IF NEW.project_id IS DISTINCT FROM OLD.project_id THEN
        RAISE EXCEPTION 'project_id is immutable';
    END IF;
    -- repo_id can become NULL via FK SET NULL cascade (when repo is hard-deleted), but not change to different repo
    IF NEW.repo_id IS DISTINCT FROM OLD.repo_id AND NEW.repo_id IS NOT NULL THEN
        RAISE EXCEPTION 'repo_id is immutable (cannot change to different repo)';
    END IF;
    IF NEW.alias IS DISTINCT FROM OLD.alias THEN
        RAISE EXCEPTION 'alias is immutable';
    END IF;
    IF NEW.workspace_type IS DISTINCT FROM OLD.workspace_type THEN
        RAISE EXCEPTION 'workspace_type is immutable';
    END IF;

    -- Auto-soft-delete when repo_id becomes NULL (repo was hard-deleted)
    IF OLD.repo_id IS NOT NULL AND NEW.repo_id IS NULL AND NEW.deleted_at IS NULL THEN
        NEW.deleted_at = NOW();
    END IF;

    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS workspace_updated_at ON {{tables.workspaces}};
CREATE TRIGGER workspace_updated_at
    BEFORE UPDATE ON {{tables.workspaces}}
    FOR EACH ROW
    EXECUTE FUNCTION {{schema}}.update_workspace_timestamp();

CREATE TABLE IF NOT EXISTS {{tables.bead_claims}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- CASCADE: claims deleted when project is deleted
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    -- CASCADE: claims deleted when workspace is deleted
    workspace_id UUID NOT NULL REFERENCES {{tables.workspaces}}(workspace_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    human_name TEXT NOT NULL,
    bead_id TEXT NOT NULL,
    -- Apex reference for fast team status listings
    apex_bead_id TEXT,
    apex_repo_name TEXT,
    apex_branch TEXT,
    claimed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    -- Multiple workspaces can claim the same bead (coordinated work with --:jump-in)
    UNIQUE(project_id, bead_id, workspace_id)
);

CREATE INDEX IF NOT EXISTS idx_bead_claims_workspace
    ON {{tables.bead_claims}}(workspace_id, claimed_at DESC);
CREATE INDEX IF NOT EXISTS idx_bead_claims_project ON {{tables.bead_claims}}(project_id);

CREATE TABLE IF NOT EXISTS {{tables.escalations}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES {{tables.workspaces}}(workspace_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    member_email TEXT,
    subject TEXT NOT NULL,
    situation TEXT NOT NULL,
    options JSONB,
    status TEXT DEFAULT 'pending',
    response TEXT,
    response_note TEXT,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    responded_at TIMESTAMPTZ,
    expires_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_escalations_status ON {{tables.escalations}}(status);
CREATE INDEX IF NOT EXISTS idx_escalations_member ON {{tables.escalations}}(member_email);
CREATE INDEX IF NOT EXISTS idx_escalations_workspace ON {{tables.escalations}}(workspace_id);
CREATE INDEX IF NOT EXISTS idx_escalations_alias_created
    ON {{tables.escalations}}(alias, created_at DESC);

CREATE TABLE IF NOT EXISTS {{tables.subscriptions}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    workspace_id UUID NOT NULL REFERENCES {{tables.workspaces}}(workspace_id) ON DELETE CASCADE,
    alias TEXT NOT NULL,
    bead_id TEXT NOT NULL,
    repo TEXT,
    event_types TEXT[] NOT NULL DEFAULT '{status_change}',
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_subscriptions_unique
    ON {{tables.subscriptions}}(project_id, workspace_id, bead_id, COALESCE(repo, ''));
CREATE INDEX IF NOT EXISTS idx_subscriptions_bead
    ON {{tables.subscriptions}}(project_id, bead_id, repo);
CREATE INDEX IF NOT EXISTS idx_subscriptions_workspace
    ON {{tables.subscriptions}}(project_id, workspace_id, created_at DESC);

CREATE TABLE IF NOT EXISTS {{tables.notification_outbox}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- Tenant isolation
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    -- Event details
    event_type TEXT NOT NULL DEFAULT 'bead_status_change',
    -- Full payload for the notification (bead_id, status change, etc.)
    payload JSONB NOT NULL,
    -- Target workspace for the notification (no FK - subscriptions may outlive workspaces)
    recipient_workspace_id UUID NOT NULL,
    recipient_alias TEXT NOT NULL,
    -- Processing status
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    -- Timestamps
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    processed_at TIMESTAMPTZ,
    -- Message ID if successfully sent (no FK - messages may be deleted)
    message_id UUID
);

CREATE INDEX IF NOT EXISTS idx_notification_outbox_pending
    ON {{tables.notification_outbox}}(project_id, status, attempts, created_at)
    WHERE status IN ('pending', 'failed');
CREATE INDEX IF NOT EXISTS idx_notification_outbox_completed
    ON {{tables.notification_outbox}}(project_id, status, processed_at)
    WHERE status = 'completed';

CREATE TABLE IF NOT EXISTS {{tables.audit_log}} (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    workspace_id UUID REFERENCES {{tables.workspaces}}(workspace_id) ON DELETE SET NULL,
    event_type TEXT NOT NULL,
    alias TEXT,
    member_email TEXT,
    resource TEXT,
    bead_id TEXT,
    details JSONB,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_audit_log_created ON {{tables.audit_log}}(created_at);
CREATE INDEX IF NOT EXISTS idx_audit_log_alias ON {{tables.audit_log}}(alias);
CREATE INDEX IF NOT EXISTS idx_audit_log_project ON {{tables.audit_log}}(project_id);

CREATE TABLE IF NOT EXISTS {{tables.project_policies}} (
    policy_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(id) ON DELETE CASCADE,
    version INT NOT NULL,
    bundle_json JSONB NOT NULL,
    created_by_workspace_id UUID REFERENCES {{tables.workspaces}}(workspace_id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),
    CONSTRAINT project_policies_version_unique UNIQUE (project_id, version)
);

-- Add FK after project_policies to avoid circular dependency during create
ALTER TABLE {{tables.projects}}
    ADD CONSTRAINT fk_projects_active_policy
    FOREIGN KEY (active_policy_id)
    REFERENCES {{tables.project_policies}}(policy_id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_project_policies_project_version
    ON {{tables.project_policies}}(project_id, version DESC);
CREATE INDEX IF NOT EXISTS idx_project_policies_created_by
    ON {{tables.project_policies}}(created_by_workspace_id)
    WHERE created_by_workspace_id IS NOT NULL;

CREATE OR REPLACE FUNCTION {{schema}}.project_policies_update_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS project_policies_update_timestamp ON {{tables.project_policies}};
CREATE TRIGGER project_policies_update_timestamp
    BEFORE UPDATE ON {{tables.project_policies}}
    FOR EACH ROW
    EXECUTE FUNCTION {{schema}}.project_policies_update_timestamp();
