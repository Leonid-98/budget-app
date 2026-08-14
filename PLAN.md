# Budget App — Plan

Replaces the shared Google Sheet (one sheet per month, left/right halves per person,
rows per expense type, colors for paid status) with a web app on the existing
personal server behind oauth2-proxy.

## How sheet concepts map to the app

| Google Sheet                          | App                                              |
| ------------------------------------- | ------------------------------------------------ |
| One sheet per month (past + future)    | Month entity; browse/create months, plan ahead   |
| Left half = Leonid, right half = wife  | Two person columns on the month view             |
| Доход row                              | Per-person income value, edited in Settings      |
| Blocks per expense type                | Ordered groups (Счета, Рассрочки, Траты, …)      |
| Cell color = paid / not paid           | Status chip on each expense (paid / pending)     |
| "this is in Swedbank" cell comments    | Optional tag on an entry (swedbank, coop pank)   |
| Formulas (free money, transfer amount) | Computed settlement: who sends whom, how much    |

## v1 functionality

1. **Month view** — two person columns. Income is a single line per person at
   the top (a value, not an entry list — it changes rarely and is edited in
   Settings). Expenses are grouped under the pre-defined **ordered groups**
   (Счета, Рассрочки, Траты, Долги, Отложить). Each expense is: name, amount,
   status (paid / pending), optional tag showing where the money sits.
2. **Inline editing** — click an expense to edit it in place (htmx partial
   updates); the summary recalculates on every change.
3. **Summary block** — below the ledger: a small table with a column per
   person and rows Income / Expenses / Free, followed by the transfer line
   in plain text: "<Name> to send <Name> <amount>" (amount in accent color,
   same font as the rest). No ratio shown in the UI; the split (default
   50/50) lives in server config only.
4. **Settings pop-up** — opened from a gear icon in the header; one place to
   manage the rarely-changed things: per-person income (new months take the
   latest value), groups (create/rename/reorder/archive), tags (coop, swed,
   misc, …). All changes go through the same audit log.
5. **Month management** — create next month as a copy of a previous one
   (entries and income copied, statuses reset to pending) or blank; navigate
   months. Opening the app lands on the month you last viewed (stored per
   user; guests get the current calendar month).
6. **Change history** — append-only audit log for every create/update/delete:
   who (email from oauth2-proxy header, else device-ID cookie), when,
   field, old value → new value. Shown in a **global** "History" pop-up
   opened from the header, next to Settings — one list across all months,
   limited to the last two months in the UI; the full log stays in the
   database. Emails are stored but **never displayed** — the UI always shows
   the display name (or the device ID when not signed in).
7. **Locale-friendly input** — amount fields accept comma decimals ("11,5"),
   as used in the sheet.
8. **Personal settings pop-up** — opened by clicking your name in the top
   right, strictly separate from the global (shared-data) Settings pop-up.
   Contains per-user UI preferences: accent color (teal default; violet,
   ocean, coral, graphite, rose) and theme (system default / light / dark).
   Design is the "Soft" theme — rounded, pill-shaped controls — with light
   and dark variants for every accent.
9. **No hint texts** — the UI carries no helper captions or explanatory
   labels anywhere; controls must be self-explanatory.
10. **Russian UI** — all interface strings are hardcoded Russian (no locale
    framework): app name "Траты", Доход / Расходы / Остаток, statuses
    оплачено / ожидает, История, Настройки, etc.

## Settlement formula (confirmed)

The goal is that both persons end the month with the **same amount of free
money** after all mapped expenses (ratio configurable, default 50/50, not
shown in the UI):

```
free_A     = income_A − expenses_A
free_B     = income_B − expenses_B
target     = ratio_A × (free_A + free_B)        # 0.5 by default
transfer   = free_A − target                    # positive → A sends B
```

Worked example (real August sheet, `Траты - Август.csv`): Лёня 2,993.00 income,
1,799.50 expenses → 1,193.50 free. Аня 574.00 income, 1,150.50 expenses →
−576.50 free (negative is fine, the math still works). Pool 617.00, target
308.50 each → **Лёня sends 885.00**; both end with 308.50 — matching the
sheet's Остаток (308.5 / 308.5) and Пропорция (2108 kept / 885 sent) rows.

## Later phases (explicitly not v1)

- CSV import of historical Google Sheets months (export format known —
  see `Траты - Август.csv`; colors and formulas are absent from exports)
- "Money by account" balance block (like the sheet's SEB 2 / SWED / Bigbank
  side column) — if per-entry tags turn out not to be enough
- Charts: type spend across months, plan vs actual
- Recurring-expense templates beyond "copy previous month"
- Restore/undo from the audit log (v1 log is for traceability only)

## Assumptions (to confirm)

1. **Two fixed users**, identified by `X-Forwarded-Email` from oauth2-proxy.
   The app trusts the proxy completely — no sessions, passwords, or roles of its own.
   The two emails + display names + column side + split ratio come from env config.
2. **Anyone the proxy lets in can edit everything** (same trust model as the shared sheet).
3. **Single currency EUR**, amounts stored as integer cents (no floats).
4. **All income and expense entries count** toward the settlement — one-off
   irregular income (like a tax refund) simply isn't entered.
5. **Each entry belongs to exactly one person's column**, like the sheet.
6. **Groups and tags are shared lists** used by both persons and all months,
   managed only in the Settings pop-up.
7. **Status is binary** — paid/pending, expenses only. Income has no status.
8. **Deployment stays as-is**: one Flask container behind the proxy; SQLite database
   file on a mounted Docker volume; backup = copy that one file.
9. When no email header is present (e.g. direct LAN access), the actor is recorded
   as a per-browser device-ID cookie ("MacBook-Air …").

## Data model (SQLite)

```
users         (id, email, display_name, side,
               accent_color DEFAULT 'teal',
               theme DEFAULT 'system')                    -- seeded from env
months        (id, year, month, note)
month_incomes (month_id, user_id, income_cents)          -- snapshot per month
groups        (id, name, sort_order, archived)           -- Счета, Рассрочки, …
tags          (id, name, sort_order)                     -- swed, coop, seb 2, misc, …
entries       (id, month_id, user_id, group_id, name, amount_cents,
               status, tag_id, sort_order, created_at, updated_at)  -- tag_id nullable
audit_log     (id, at, actor, action, entry_id, month_id, field, old_value, new_value)
```

Income is snapshotted per month so past months keep their historical values;
editing income in Settings updates the currently open (and future) months only.

## Architecture (as built)

- **Flask + Jinja2, plain forms + redirects, htmx on top** — every action is
  a normal form POST followed by a redirect back to the month (dialogs reopen
  via a `?dlg=` query param). A vendored htmx (`hx-boost` on one `#page`
  wrapper, `hx-select`/`hx-target` back onto itself) turns those same
  navigations into in-place partial swaps — no visible reloads, scroll
  preserved — with zero server-side changes; plain forms remain the no-JS
  fallback. ~60 lines of vanilla JS (event-delegated, swap-safe) handle
  dialogs, inline form toggles, and instant accent/theme switching.
- **Flask-SQLAlchemy** with `create_all()` on startup; **SQLite** on a Docker
  volume (`/data/budget.db`), backup = copy the file. Alembic deferred until
  the schema first needs to change.
- **Identity middleware**: reads `X-Forwarded-Email` (header name configurable
  via `IDENTITY_HEADER`), falls back to a device-ID cookie; audit actors are
  emails or device labels, rendered as display names only.
- **Gunicorn** (1 worker, 4 threads) in the container.
- **pytest**: settlement verified against the real August sheet numbers,
  month copy, income propagation, audit trail, identity, prefs.
- Config via env in docker-compose: user emails/names (incl. dative form for
  the transfer sentence), split ratio, identity header, DB path.
- Package layout: `app/` (`__init__` factory, `models`, `services`, `routes`,
  `templates/`, `static/`), `tests/`, `wsgi.py`.

## Open questions

1. In the sheet's summary block, Остаток row has a third value `12,34` next to
   the 308.5/308.5 pair — what is it? (Ignored for now.)
