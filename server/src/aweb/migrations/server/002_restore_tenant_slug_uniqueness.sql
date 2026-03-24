-- 002_restore_tenant_slug_uniqueness.sql
-- Description: Restore tenant-scoped project slug uniqueness in the OSS server
-- schema and remove the owner-UUID uniqueness drift introduced later in the
-- original baseline.

DROP INDEX IF EXISTS {{schema}}.idx_projects_slug_with_user_owner;
DROP INDEX IF EXISTS {{schema}}.idx_projects_slug_with_org_owner;
DROP INDEX IF EXISTS {{schema}}.idx_projects_owner_user_active;
DROP INDEX IF EXISTS {{schema}}.idx_projects_owner_org_active;

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug_no_tenant
    ON {{tables.projects}}(slug)
    WHERE tenant_id IS NULL AND deleted_at IS NULL;

CREATE UNIQUE INDEX IF NOT EXISTS idx_projects_slug_with_tenant
    ON {{tables.projects}}(tenant_id, slug)
    WHERE tenant_id IS NOT NULL AND deleted_at IS NULL;
