-- 0007_company_profile.sql
-- Single source of truth for company branding + financial defaults.
-- Replaces hardcoded strings in n8n Code nodes and PDF/email templates.
-- Single-row table: id is pinned to 1 by the CHECK, so there is always exactly
-- one profile. Read it anywhere with: SELECT * FROM company_profile WHERE id = 1;

CREATE TABLE IF NOT EXISTS company_profile (
    id SMALLINT PRIMARY KEY DEFAULT 1 CHECK (id = 1),   -- enforce single row
    -- Identity / branding
    company_name        VARCHAR(255) NOT NULL DEFAULT 'Ireh Construction',
    legal_name          VARCHAR(255) NOT NULL DEFAULT 'Ireh Construction',
    street_address      TEXT NOT NULL DEFAULT '1951 Kaptey Ave',
    city                VARCHAR(100) NOT NULL DEFAULT 'Coquitlam',
    province            VARCHAR(50)  NOT NULL DEFAULT 'BC',
    postal_code         VARCHAR(20) NOT NULL DEFAULT 'V3K 5Z7',
    phone               VARCHAR(50) NOT NULL DEFAULT '778-994-6602',
    email_from          VARCHAR(255) NOT NULL DEFAULT 'support.ordrnow@gmail.com',
    email_from_name     VARCHAR(255) NOT NULL DEFAULT 'Ireh Construction',
    website             VARCHAR(255),
    portal_base_url     VARCHAR(255) NOT NULL DEFAULT 'https://n8n2.ordrnow.com',
    signature_name      VARCHAR(255) NOT NULL DEFAULT 'Dave',
    -- Document numbering
    invoice_prefix      VARCHAR(20) NOT NULL DEFAULT 'INV-',
    quote_prefix        VARCHAR(20) NOT NULL DEFAULT 'QUO-',
    change_order_prefix VARCHAR(20) NOT NULL DEFAULT 'CR-',
    project_prefix      VARCHAR(20) NOT NULL DEFAULT 'PRJ-',
    -- Branding colors (emails / PDFs / portal)
    brand_primary_color VARCHAR(9)  NOT NULL DEFAULT '#1a3a5c',
    brand_accent_color  VARCHAR(9)  NOT NULL DEFAULT '#2563eb',
    brand_success_color VARCHAR(9)  NOT NULL DEFAULT '#16a34a',
    -- Financial defaults (BC)
    gst_rate            NUMERIC(5,4) NOT NULL DEFAULT 0.05,
    pst_rate            NUMERIC(5,4) NOT NULL DEFAULT 0.07,
    retention_rate      NUMERIC(5,4) NOT NULL DEFAULT 0.10,
    invoice_due_days    INT NOT NULL DEFAULT 30,
    -- Payroll defaults
    cpp_rate            NUMERIC(5,4) NOT NULL DEFAULT 0.0595,
    ei_rate             NUMERIC(5,4) NOT NULL DEFAULT 0.0163,
    wcb_rate            NUMERIC(5,4) NOT NULL DEFAULT 0.0325,
    payroll_period      VARCHAR(20)  NOT NULL DEFAULT 'MONTHLY',  -- WEEKLY / BIWEEKLY / MONTHLY
    payroll_day_of_month INT NOT NULL DEFAULT 1,
    ot_multiplier       NUMERIC(3,2) NOT NULL DEFAULT 1.5,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Seed the single row with Ireh Construction defaults (idempotent).
INSERT INTO company_profile (id)
SELECT 1
WHERE NOT EXISTS (SELECT 1 FROM company_profile WHERE id = 1);
