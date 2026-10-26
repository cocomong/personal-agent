-- 0033_projects_soft_delete.sql
-- Soft delete for projects: a removed project keeps its row (and every
-- dependent invoice/estimate/change order/approval) but disappears from every
-- gateway tool. All project-resolution SQL filters deleted_at IS NULL.
-- Additive only — no data migration (existing rows stay active, NULL marker).

ALTER TABLE projects
    ADD COLUMN IF NOT EXISTS deleted_at timestamptz;

COMMENT ON COLUMN projects.deleted_at IS
    'Soft-delete marker: non-NULL = project removed. Hidden from all gateway tools; row and history kept.';
