-- 0035_company_logo.sql
-- Store the company logo as bytes on company_profile so invoices can embed it
-- as a data: URI at render time. An ISSUED invoice (invoices.last_client_html)
-- must be self-contained: it can never depend on an externally linked image
-- that could move, change, or 404 later.
--
-- The logo file lives in the repo at backend/branding/house-logo.svg and is
-- seeded into company 1 by backend/n8n/seed_company_logo.py (idempotent).

ALTER TABLE company_profile
    ADD COLUMN IF NOT EXISTS logo_data text,
    ADD COLUMN IF NOT EXISTS logo_content_type text;

COMMENT ON COLUMN company_profile.logo_data IS
    'Base64-encoded logo bytes (SVG/PNG). Rendered into invoice HTML as data:<type>;base64,<bytes> so archived invoices are self-contained.';
COMMENT ON COLUMN company_profile.logo_content_type IS
    'MIME type of logo_data (e.g. image/svg+xml, image/png). NULL when no logo is on file.';
