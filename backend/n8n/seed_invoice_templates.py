#!/usr/bin/env python3
"""Seed the invoice template catalog into document_templates (idempotent).

Reads the curated layouts from backend/templates/ and prints one upsert per
template on stdout (ON CONFLICT (key) DO UPDATE — re-run after any template
edit; only the catalog rows change). Pipe straight into the live database:

    python3 backend/n8n/seed_invoice_templates.py | \\
      ssh ubuntu@n8n2.ordrnow.com \\
        "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1 -q"
"""
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

# file -> (key, display name, one-line description)
CATALOG = [
    ("invoice.html", "classic",
     "Classic",
     "Clean traditional layout: bordered header, line-items table, boxed payment instructions."),
    ("invoice-modern.html", "modern",
     "Modern",
     "Bold color band header with the logo framed, dark table header, colored totals card."),
    ("invoice-compact.html", "compact",
     "Compact",
     "Condensed one-page fit: tighter type, single-line header, minimal decoration."),
]


def esc(s: str) -> str:
    return s.replace("'", "''")


print("-- seed invoice template catalog (idempotent upsert by key)")
for file, key, name, desc in CATALOG:
    html = (TEMPLATES_DIR / file).read_text()
    print(f"INSERT INTO document_templates (key, display_name, description, html) VALUES (")
    print(f"  '{key}', '{esc(name)}', '{esc(desc)}',")
    print(f"  $tpl${html}$tpl$)")
    print("ON CONFLICT (key) DO UPDATE SET")
    print("  display_name = EXCLUDED.display_name, description = EXCLUDED.description,")
    print("  html = EXCLUDED.html, is_active = true, updated_at = CURRENT_TIMESTAMP;")
print()
print("-- every key must remain unique and active after seeding")
print("DO $$ BEGIN")
print("  IF (SELECT count(*) FROM document_templates WHERE key IN ('classic','modern','compact')) <> 3 THEN")
print("    RAISE EXCEPTION 'template catalog seed incomplete'; END IF;")
print("END $$;")
