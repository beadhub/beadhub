-- 005_project_roles_rename.sql
-- Rename legacy policy schema objects to canonical project_roles names.

DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = '{{schema}}'
          AND table_name = 'policies'
    ) THEN
        EXECUTE format(
            'ALTER TABLE %I.%I RENAME TO %I',
            '{{schema}}',
            'policies',
            'project_roles'
        );
    END IF;
END
$$;

DO $$
DECLARE
    old_active_column text := 'active_' || 'pol' || 'icy_id';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = '{{schema}}'
          AND table_name = 'projects'
          AND column_name = old_active_column
    ) THEN
        EXECUTE format(
            'ALTER TABLE %I.%I RENAME COLUMN %I TO %I',
            '{{schema}}',
            'projects',
            old_active_column,
            'active_project_roles_id'
        );
    END IF;
END
$$;

DO $$
DECLARE
    old_id_column text := 'pol' || 'icy_id';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = '{{schema}}'
          AND table_name = 'project_roles'
          AND column_name = old_id_column
    ) THEN
        EXECUTE format(
            'ALTER TABLE %I.%I RENAME COLUMN %I TO %I',
            '{{schema}}',
            'project_roles',
            old_id_column,
            'project_roles_id'
        );
    END IF;
END
$$;

-- Rename the constraint to match the new table/column names.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = '{{schema}}'
          AND constraint_name = 'fk_projects_active_policy'
    ) THEN
        EXECUTE format(
            'ALTER TABLE %I.%I RENAME CONSTRAINT %I TO %I',
            '{{schema}}',
            'projects',
            'fk_projects_active_policy',
            'fk_projects_active_project_roles'
        );
    END IF;
END
$$;
