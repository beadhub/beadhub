UPDATE {{tables.workspaces}}
SET workspace_type = 'dashboard_browser'
WHERE workspace_type = 'dashboard';

DROP INDEX IF EXISTS idx_workspaces_dashboard;

ALTER TABLE {{tables.workspaces}}
DROP CONSTRAINT IF EXISTS chk_workspace_repo;

ALTER TABLE {{tables.workspaces}}
ADD CONSTRAINT chk_workspace_repo CHECK (
    deleted_at IS NOT NULL OR
    (
        (workspace_type = 'agent' AND repo_id IS NOT NULL) OR
        (
            workspace_type IN (
                'dashboard_browser',
                'hosted_mcp',
                'local_dir',
                'service_process',
                'manual'
            )
            AND repo_id IS NULL
        )
    )
);
