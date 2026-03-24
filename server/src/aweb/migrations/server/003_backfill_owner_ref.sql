-- 003_backfill_owner_ref.sql
-- Description: Backfill the generic owner_ref field from legacy owner UUID
-- columns so OSS runtime code can rely on owner_type + owner_ref as the
-- authoritative grouping coordinates.

UPDATE {{tables.projects}}
SET owner_ref = owner_user_id::text
WHERE owner_type = 'user'
  AND owner_ref IS NULL
  AND owner_user_id IS NOT NULL;

UPDATE {{tables.projects}}
SET owner_ref = owner_org_id::text
WHERE owner_type = 'organization'
  AND owner_ref IS NULL
  AND owner_org_id IS NOT NULL;
