# Invoice dates + push targeting — investigation and fix plan

**Status:** IMPLEMENTED AND LIVE 2026-10-30 (see section 6). No device pass yet -
install the new APK on both phones and open it once so they re-register.

Two separate defects, both confirmed against the live system:

1. Draft invoice previews print raw ISO timestamps for the invoice/due dates.
2. A phone signed in as a different account (and since logged out) still receives
   invoice pushes belonging to Ireh Construction.

---

## 1. Evidence

### 1.1 Dates

The stored client HTML for the invoice created today contains:

```
2026-10-29T07:00:00.000Z      <- issued_date
2026-11-28T07:00:00.000Z      <- due_date
```

Chain:
- `invoices.issued_date` / `due_date` are `date` columns (verified:
  `issued_date:date`, `due_date:date`).
- The gateway query (`Exec: invoice_push_lookup` / `Exec: send_customer_invoice_lookup`)
  selects them raw.
- node-postgres returns a `Date` object; n8n serialises it to JSON → a full ISO
  timestamp at local midnight (`07:00Z` = 00:00 PDT).
- `Render Invoice HTML` → `buildInvoiceData()` passes it straight through:

```js
issued_date: inv?.issued_date ?? '',
due_date:   inv?.due_date ?? '',
```

- The template prints the value verbatim: `{{issued_date}}` / `{{due_date}}`
  (`backend/templates/invoice.html:119-120`).

The same raw value is rendered by the receipt email builder, which only slices it
(`const d = (v) => String(v).slice(0, 10)`) → `2026-10-29` (ISO, not wrong but not
what a client expects on a document), and by the push-invoice renderer (a second
copy of the same render code inside the gateway).

### 1.2 Pushes reaching the wrong phone

Three independent gaps, all live:

| # | Where | What happens |
|---|-------|--------------|
| 1 | `db/0021` → `device_tokens` | The table has **no `user_id`**; only `company_id SMALLINT NOT NULL DEFAULT 1`. |
| 2 | `backend/n8n/workflows/device-registration.json` → `Exec: upsert_device_token` | `INSERT INTO device_tokens (token, platform, device_name) …` — the app **does send** `X-User-Token`, but the workflow ignores it. Every phone that registers lands in company 1. |
| 3 | Gateway push nodes (`Exec: push_devices`, `Exec: template_push_devices`, `Exec: get_device_tokens`, `Exec: approval_devices`) | Fan out to **every token in the company**. With #2, that is every phone that ever registered — including the second phone and four stale tokens from August. |
| 4 | `mobile-flutter/lib/auth/auth_service.dart:100-103` | `signOut()` clears the local session only. The FCM token stays registered server-side forever. |

Live `device_tokens` (6 rows, all company 1, none tied to a user):

```
cHIOXspQR2qw... | 1 | android | phone | 2026-08-30
eMVdz5sGSVSt... | 1 | android | phone | 2026-08-30
dh7-OIvER1Og... | 1 | android | phone | 2026-10-27
cZwSYesNQxia... | 1 | android | phone | 2026-10-18
fwuisE2bQnKW... | 1 | android | phone | 2026-10-29
dX4gzC_uQgSq... | 1 | android | phone | 2026-10-29
```

The push itself is triggered by the **`send_invoice_to_phone`** tool (router branch 26
→ `Exec: invoice_push_lookup` → `Push Invoice Ready?` → render → store →
`Exec: push_devices` → `Push Invoice Review`), so a draft invoice is pushed whenever the
assistant sends it to the phone — which is the intended feature; the bug is *who*
receives it.

Note: the company scoping added in commit `72ce3db` did not cause this and does not fix
it — the second phone is in company 1 because registration puts it there.

---

## 2. Fix 1 — human dates on invoices

**Rule:** dates are formatted at the presentation layer, from the calendar date, with no
timezone arithmetic (a `date` at 00:00 UTC formatted in Vancouver would show the previous
day — that is how you get an invoice dated 2026-10-28 for a 2026-10-29 run).

Approach — one shared helper, used by every renderer:

```js
const MONTHS = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
// "2026-10-29T07:00:00.000Z" | "2026-10-29" -> "Oct 29, 2026"; anything else passes through.
const fmtDate = (v) => {
  if (v === null || v === undefined || v === '') return '';
  const m = String(v).match(/^(\d{4})-(\d{2})-(\d{2})/);
  return m ? `${MONTHS[Number(m[2]) - 1]} ${Number(m[3])}, ${m[1]}` : String(v);
};
```

Apply at the **source**, not per node: `backend/n8n/patch_invoice_template.py` is the
generator that writes `buildInvoiceData` into all three render Code nodes
(`Render Invoice HTML`, `Render Push Invoice HTML` in the gateway, and
`Render Client Invoice` in `approve-invoice.json`) — it currently emits
`issued_date: inv?.issued_date ?? ''` at line 92. Add `fmtDate` there and switch both
date mappings, then re-run the patcher so every copy stays identical (that is the same
house rule that keeps the invoice layout in sync).

Also:
- Receipt builder in the gateway (`d()` → `fmtDate`) so receipts read `Oct 29, 2026`.
- `invoice-template-preview.json` builds its sample invoice with
  `new Date().toISOString().slice(0,10)` — use `fmtDate` so the chooser preview matches.
- Audit the estimate / change-order approval emails for the same raw-date pattern
  (`valid_until`, approval dates) and fix any found.

The template itself does not change: it keeps `{{issued_date}}` and receives a
presentation-ready string, so the archived HTML (and the copy stored in
`invoices.last_client_html`) is correct too.

Tests:
- `backend/templates/mustache_mini.test.js` (or a new `qa/render_dates_test.py`): run the
  real `buildInvoiceData` + renderer jsCode with a fixture containing
  `"2026-10-29T07:00:00.000Z"` and assert the HTML contains `Oct 29, 2026`, contains no
  `T07:00` and no `Z`; `null` → blank; `"2026-10-29"` → same output.
- Live: recreate a draft invoice (INV-0007), `send_invoice_to_phone`, then
  `SELECT last_client_html` and assert no ISO timestamps remain in the date block.

---

## 3. Fix 2 — pushes go only to the phones of the account they belong to

Three changes, in dependency order.

### 3.1 Bind a device token to a user (`db/0044_device_owner.sql`)

```sql
ALTER TABLE device_tokens ADD COLUMN IF NOT EXISTS user_id UUID
    REFERENCES users(id) ON DELETE CASCADE;
CREATE INDEX IF NOT EXISTS idx_device_tokens_user ON device_tokens (user_id);

-- Every existing row predates ownership and several are months stale; phones
-- re-register on the next app open (FcmService.registerAfterLogin), so the safe
-- move is to forget them all rather than guess which token is whose.
DELETE FROM device_tokens;
```

### 3.2 Registration records who the phone belongs to

`device-registration.json`:
- Verify `X-User-Token` (same HMAC code as the hook/auth-me) → `uid`.
- Resolve `users.company_id`; a user with **no company yet** (mid-onboarding) is not a
  push target: respond `{ok:true, registered:false, note:'no company'}` and store nothing.
- `INSERT INTO device_tokens (token, platform, device_name, user_id, company_id) … ON CONFLICT (token) DO UPDATE SET platform, device_name, user_id, company_id, last_seen_at`
  — so signing in as a different account on the same phone **re-homes** the token.
- `Exec: get_briefing_time` stops hardcoding `id = 1` and uses the resolved company.

### 3.3 Logout unregisters

- New workflow `device-unregister-001`: `POST /webhook/device/unregister` with
  `X-User-Token` + `{token}` → `DELETE FROM device_tokens WHERE token = $1 AND user_id = $uid`
  (a session can only remove its own device).
- App `AuthService.signOut()`: call it **before** clearing the session (the header needs
  the token), best-effort with a short timeout, then clear as today.
- Also call it when the app detects a sign-in as a *different* Google account, so a stale
  row never outlives a switch.

### 3.4 Push queries (already company-scoped, now meaningful)

`Exec: push_devices`, `Exec: template_push_devices`, `Exec: get_device_tokens`,
`Exec: approval_devices` stay scoped by company — with registration now honest, that is
the same set as "this company's phones". Optional hardening: also require
`user_id = (invoice owner)` once a company can have more than one user (out of scope
today: one user per company by design).

### Tests

| Level | Check |
|-------|-------|
| Offline | `device-registration` SQL names `user_id` + `company_id`; unregister SQL deletes by token **and** user; jsCode verification rejects a bad/absent token. |
| DB (rolled back) | Seed user A (company 1) + user B (company 2) + a token each; assert the push query returns only A's token for A's company, and that re-registering the same token as B moves it (no duplicate row, one company). |
| Live | Register a probe token for A, run `send_invoice_to_phone` as A → `push_devices` output contains A's token and not B's (probe reads the SQL result, not FCM delivery). Then unregister A's token and assert zero rows. |
| Device | Phone 2 signs out → its token disappears from `device_tokens`; create + send a draft on phone 1 → phone 2 stays silent. Sign phone 2 in as another account → it only gets that account's pushes. |

---

## 4. Rollout

1. `db/0044` (clears tokens — every phone re-registers on next app open; no user action).
2. Deploy `device-registration` + new `device-unregister`; deploy the renderer patch
   (invoice + push + receipt) in the same window.
3. App build with the unregister call; install on both phones.
4. Verify: dates on a fresh draft; phone 2 silent after logout; both phones still get
   their own pushes when signed in.

Rollback: `db/0044` adds a nullable column (re-runnable); the token DELETE is the only
destructive step and it is self-healing (re-registration). Workflow JSON is versioned in
n8n and re-deployable by id.

---

## 5. Decisions needed

1. **Date format** — `Oct 29, 2026` (recommended, matches the rest of the UI) or
   `2026-10-29` / `29/10/2026`?
2. **Clearing the 6 existing device tokens** — accepted? They re-register automatically on
   the next app open, so the only cost is one push-less session per phone.
3. **A phone signed in but with no company (mid-setup)** — should it receive pushes at all?
   Recommendation: no (nothing to push yet), register only after setup completes.
4. **Draft invoices** — keep pushing the preview when the PM explicitly asks
   (`send_invoice_to_phone`), which is today's behaviour? Recommendation: yes, unchanged.


---

## 6. As built (2026-10-30)

Decisions taken: `Oct 29, 2026`; clear the legacy device tokens; no pushes for a phone
that has not completed setup; keep pushing a draft preview when the PM asks for it.

**Dates**
- `backend/n8n/patch_invoice_template.py` now emits `fmtDate()` into the data-prep shared
  by all three render nodes (`Render Invoice HTML`, `Render Push Invoice HTML`,
  `Render Client Invoice`), so the date formatting cannot drift between copies. Its
  idempotency guard had to be widened — it used to skip any node that already carried the
  template, which would have left the old data-prep in place.
- `backend/n8n/patch_document_dates.py` does the same for the receipt renderer and the
  template-chooser sample invoice.
- `fmtDate` reads the `YYYY-MM-DD` prefix and prints `Mon D, YYYY`, deliberately without
  timezone maths (a `date` arrives as 00:00Z; local conversion would print the day before).
- Verified live: INV-0006 re-rendered to `Issued Oct 29, 2026 / Due Nov 28, 2026`, no ISO
  timestamps left; `backend/n8n/test_document_dates.py` covers ISO input, blanks, an
  already-formatted value, and the receipt.

**Push ownership**
- `db/0044_device_owner.sql`: `device_tokens.user_id` (+ indexes) and the six legacy
  unowned rows deleted (phones re-register on next open).
- `device-registration.json`: verifies the session token, refuses unauthenticated
  registration (401), writes `user_id` + the caller's `company_id`, re-homes a token when
  the same phone signs in as someone else, and stores nothing for a user who has not
  finished setup. `get_briefing_time` is scoped to that company (was `id = 1`).
- `device-unregister.json` (new): `POST /webhook/device/unregister` deletes only the
  caller's own row for that token; idempotent.
- App: `FcmService.unregisterDevice()` + `AuthService.signOut()` calls it before the
  session is cleared, so a signed-out phone stops receiving pushes.
- Live probe `qa/device_owner_probe.py`: owner + a second company register separately,
  company 1's push list excludes company 2's phone, a no-company user is not stored,
  unauthenticated registration is refused, unregister removes exactly one row, one user
  cannot unregister another's phone, and a cross-user re-registration re-homes the token
  (still one row).

Regression at the time of writing: document dates, onboarding scope (offline), onboarding
scope (rolled-back DB), onboarding live probe, device-owner live probe — all green.

Still to do on the device: install the new APK, open the app once per phone (this is what
re-registers the token), sign the second phone out, then create and send a draft on the
owner's phone and confirm the second phone stays silent.
