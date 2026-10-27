-- 0037_invoice_templates.sql
-- Invoice template catalog + per-company selection.
-- All templates share ONE placeholder contract (see backend/templates/invoice.html);
-- only the layout differs. The renderer falls back to the embedded Classic when
-- a company has no selection or the selected row is inactive/missing, so
-- invoice rendering NEVER hard-depends on this table existing.

CREATE TABLE IF NOT EXISTS document_templates (
    id          uuid PRIMARY KEY DEFAULT uuid_generate_v4(),
    key         text NOT NULL UNIQUE,
    display_name text NOT NULL,
    description text NOT NULL DEFAULT '',
    html        text NOT NULL,
    is_active   boolean NOT NULL DEFAULT true,
    created_at  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at  timestamptz NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE document_templates IS
    'Curated invoice layout catalog. key: classic|modern|compact. Seeded from backend/templates/*.html by backend/n8n/seed_invoice_templates.py (idempotent upsert). Same placeholder contract for every row.';
COMMENT ON COLUMN document_templates.is_active IS
    'false = hidden from the catalog; companies pointing at it fall back to the embedded Classic.';

ALTER TABLE company_profile
    ADD COLUMN IF NOT EXISTS invoice_template_key text
        REFERENCES document_templates(key) ON DELETE SET NULL;

COMMENT ON COLUMN company_profile.invoice_template_key IS
    'Chosen invoice layout (document_templates.key). NULL = Classic default. Set during onboarding or via set_invoice_template; issued invoices keep their stored last_client_html regardless of later switches.';
