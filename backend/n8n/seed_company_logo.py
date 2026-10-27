#!/usr/bin/env python3
"""Seed the company logo into company_profile (idempotent).

Reads backend/branding/house-logo.svg, base64-encodes it, and prints a single
UPDATE statement on stdout. Pipe it straight into the live database:

    python3 backend/n8n/seed_company_logo.py | \\
      ssh ubuntu@n8n2.ordrnow.com \\
        "sudo docker exec -i n8n-compose-postgres-1 psql -U postgres -d postgres -v ON_ERROR_STOP=1"

The logo renders into invoice HTML as a data: URI (self-contained archived
invoices — an issued invoice never depends on an externally linked image).
"""
import base64
from pathlib import Path

LOGO = Path(__file__).resolve().parent.parent / "branding" / "house-logo.svg"
COMPANY_ID = 1
MIME = "image/svg+xml"

data = LOGO.read_bytes()
b64 = base64.b64encode(data).decode()
print(f"-- seed company logo from {LOGO.name} ({len(data)} bytes)")
print(
    f"UPDATE company_profile SET logo_data = '{b64}', logo_content_type = '{MIME}' "
    f"WHERE id = {COMPANY_ID};"
)
