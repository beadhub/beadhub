CREATE TABLE IF NOT EXISTS {{tables.replacement_announcements}} (
    announcement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    project_id UUID NOT NULL REFERENCES {{tables.projects}}(project_id),
    old_agent_id UUID NOT NULL REFERENCES {{tables.agents}}(agent_id),
    new_agent_id UUID NOT NULL REFERENCES {{tables.agents}}(agent_id),
    namespace_id UUID NOT NULL REFERENCES {{tables.dns_namespaces}}(namespace_id),
    address_name TEXT NOT NULL,
    old_did TEXT NOT NULL,
    new_did TEXT NOT NULL,
    controller_did TEXT NOT NULL,
    replacement_timestamp TEXT NOT NULL,
    controller_signature TEXT NOT NULL,
    authorized_by TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_replacement_announcements_new_agent
ON {{tables.replacement_announcements}} (new_agent_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_replacement_announcements_old_agent
ON {{tables.replacement_announcements}} (old_agent_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_replacement_announcements_address_new_did
ON {{tables.replacement_announcements}} (namespace_id, address_name, new_did);
