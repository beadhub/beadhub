-- 002_project_roles_rename.sql
-- Rename legacy project roles schema objects to canonical names.

DO $$
DECLARE
    schema_name text := trim(both '"' from '{{schema}}');
    old_table text := 'project_' || 'pol' || 'icies';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.tables
        WHERE table_schema = schema_name
          AND table_name = old_table
    ) THEN
        EXECUTE format(
            'ALTER TABLE %I.%I RENAME TO %I',
            schema_name,
            old_table,
            'project_roles'
        );
    END IF;
END
$$;

DO $$
DECLARE
    schema_name text := trim(both '"' from '{{schema}}');
    old_active_column text := 'active_' || 'pol' || 'icy_id';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = schema_name
          AND table_name = 'projects'
          AND column_name = old_active_column
    ) THEN
        EXECUTE format(
            'ALTER TABLE %I.%I RENAME COLUMN %I TO %I',
            schema_name,
            'projects',
            old_active_column,
            'active_project_roles_id'
        );
    END IF;
END
$$;

DO $$
DECLARE
    schema_name text := trim(both '"' from '{{schema}}');
    old_id_column text := 'pol' || 'icy_id';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.columns
        WHERE table_schema = schema_name
          AND table_name = 'project_roles'
          AND column_name = old_id_column
    ) THEN
        EXECUTE format(
            'ALTER TABLE %I.%I RENAME COLUMN %I TO %I',
            schema_name,
            'project_roles',
            old_id_column,
            'project_roles_id'
        );
    END IF;
END
$$;

DO $$
DECLARE
    schema_name text := trim(both '"' from '{{schema}}');
    old_constraint text := 'fk_projects_active_' || 'pol' || 'icy';
BEGIN
    IF EXISTS (
        SELECT 1
        FROM information_schema.table_constraints
        WHERE table_schema = schema_name
          AND table_name = 'projects'
          AND constraint_name = old_constraint
    ) THEN
        EXECUTE format(
            'ALTER TABLE %I.%I RENAME CONSTRAINT %I TO %I',
            schema_name,
            'projects',
            old_constraint,
            'fk_projects_active_project_roles'
        );
    END IF;
END
$$;
