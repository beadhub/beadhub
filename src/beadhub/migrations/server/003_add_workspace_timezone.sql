-- 003_add_workspace_timezone.sql
-- Description: Add IANA timezone to workspaces for status enrichment.

ALTER TABLE {{tables.workspaces}} ADD COLUMN IF NOT EXISTS timezone TEXT;
