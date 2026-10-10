# gmiremail: Multi-Tenant Email Marketing Platform

A self-hosted email marketing backend: Flask, PostgreSQL, SQLAlchemy and APScheduler, with sending over each business's own SMTP server.
It is built from the specs in [`docs/`](docs/).

It comes with a web dashboard at `/app/` and a REST API. It covers multi-tenant accounts (JWT or API key), subscribers (CRUD, CSV/JSON import, CSV export), templates (sandboxed Jinja2 with a starter library),
segments (JSON filter rules compiled to SQL), campaigns (send now, schedule, pause/resume, A/B subject lines),
open/click tracking, one-click unsubscribe, bounce handling with retries, automation workflows, analytics and background jobs.

## Quick start

```bash
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env              # set DATABASE_URL, SECRET_KEY, JWT_SECRET_KEY, TRACKING_DOMAIN
python app.py                     # dev server on :5000, scheduler runs in-process
```

Open <http://localhost:5000/>, create an account, and enter your SMTP details. You can also do that later under **Settings**, where **Test connection** checks them.

## Web dashboard

The dashboard is a single page served by the same Flask app, from `app/static/dashboard/`. It's plain HTML, CSS and JavaScript modules, with no build step and no external libraries.

| Page | What you can do |
|---|---|
| **Overview** | Stat tiles, daily sent/opens/clicks chart, subscriber growth, opens by hour, recent campaigns, for any period (presets or a custom date range) |
| **Subscribers** | Filter by search, status, tag, segment, **subscribed date range**, engagement score and any custom rule; filter chips; select rows or **all matching**, then bulk add/remove tag, change status, delete, or **create a campaign for them**; save the filters as a segment; add and edit, per-subscriber activity, CSV import and export |
| **Segments** | Visual rule builder with a live match count and sample, including date ranges ("subscribed between") and "not in the last N days"; JSON mode for nested groups |
| **Templates** | HTML editor with live preview (HTML and plain text), variable snippets, starter library |
| **Campaigns** | Filter by status, name/subject and date. **Audience builder**: everyone, or any mix of segments, tags, hand-picked people and a custom filter, with segment/tag exclusions and a live recipient count. Create, A/B subjects, send a test, send now, schedule, pause/resume; live stats, top links, A/B results; **retry failed**, **reset & resend** (after an SMTP problem) and **duplicate**; **export a report** per campaign as Excel (Summary, Recipients, Links sheets) or CSV |
| **Automations** | Workflow builder (send, wait, if/else, tags, fields, unsubscribe) with branching; per-subscriber run history |
| **Email logs** | Every queued or sent email, filterable by status, campaign, recipient, subject and date range |
| **Settings** | Sender identity, SMTP (with connection test), API key copy/rotate, password, sign out everywhere, **download a full backup** (server owner), **delete the account** and all its data, and the command to remove gmiremail from the server |

It follows the system light/dark theme, or you can force light or dark with the sun/moon button next to Sign out (also on the login page). It works on phones. Charts have hover tooltips and a "Show as table" view. Requests show a top progress bar, buttons show a spinner while they work, pages show skeletons while loading, and notifications are toasts with a title, icon and timer.

Run the tests (in-memory SQLite by default; set `TEST_DATABASE_URL` to use PostgreSQL):

```bash
pytest -q
TEST_DATABASE_URL=postgresql://user:pw@localhost/emk_test pytest -q
```

### Production: one server, with its own mail server

On a fresh Ubuntu or Debian VPS, one command installs everything: PostgreSQL, the web app and worker as systemd services, nginx with a Let's Encrypt certificate for your hostname, Postfix with DKIM so mail is sent directly from this server, and daily backups.

```bash
sudo git clone https://github.com/garousiamir/gmiremail /opt/gmiremail && cd /opt/gmiremail
sudo deploy/install.sh --domain mail.example.com --email you@example.com --mail-domain example.com
```

To move servers, download a backup in **Settings → Backup** and pass it to `install.sh --restore <file>` on the new server.

See **[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)** for the DNS records (SPF, DKIM, DMARC, PTR) needed for inbox delivery, IP warm-up, updates, backups and troubleshooting.

### Production: by hand

```bash
export FLASK_ENV=production AUTO_CREATE_TABLES=False ENABLE_SCHEDULER=False
flask --app wsgi db upgrade                       # apply Alembic migrations
gunicorn -w 4 -b 127.0.0.1:5000 wsgi:app          # web (note: wsgi:app, not app:app)
python worker.py                                  # background jobs: run exactly ONE
```

The `app/` package shadows `app.py`, so gunicorn has to load `wsgi:app` (the spec's `app:app` does not resolve).
The scheduler must run in a single process. Otherwise every gunicorn worker would run the jobs, and you would get duplicate dispatch and analytics work.
Concurrent queue workers are still safe on PostgreSQL, because emails are claimed with `FOR UPDATE SKIP LOCKED`.

Set `TRACKING_DOMAIN` to the public HTTPS URL of the app. Tracking pixels, click links and unsubscribe links are built from it.
Behind a reverse proxy, set `TRUSTED_PROXIES=1` so the app sees real client IPs and `https`.

## Authentication

- `POST /api/auth/register` takes `name`, `email` (login), `password` (8+ characters), and optionally `email_from`, `email_from_name`, `sender_domain`, `physical_address`, `smtp_host`, `smtp_port`, `smtp_username` (`""` means no SMTP AUTH), `smtp_password`, `smtp_tls` and `daily_email_limit`.
- `POST /api/auth/login` returns an `access_token` (15 min) and a `refresh_token` (7 days). `POST /api/auth/refresh` and `POST /api/auth/logout` (revokes all tokens) are also available.
- Send `Authorization: Bearer <access_token>` or `X-API-Key: <api_key>` with every `/api/*` call.

## API

Every endpoint listed in `docs/QUICK_REFERENCE.md` is implemented. These were added:

| Endpoint | Purpose |
|---|---|
| `POST /api/auth/logout` | Revoke all tokens |
| `POST /api/businesses/me/api-key/rotate` | Rotate the API key |
| `POST /api/businesses/me/smtp/test` | Check SMTP connect + login |
| `GET /api/subscribers/:id/activity` | Per-subscriber stats, recent emails and events |
| `GET /api/templates/library`, `POST /api/templates/library/:key` | Built-in responsive templates (welcome, newsletter, promotion) |
| `POST /api/segments/preview` | Count + sample for unsaved filter rules |
| `GET /api/segments/:id/subscribers` | Paginated segment members |
| `POST /api/campaigns/:id/test` | Send a `[TEST]` copy to up to 5 addresses |
| `POST /api/automations/events` | Fire a `custom_event` trigger: `{"event", "subscriber_id" or "email"}` |
| `GET /api/automations/:id/instances` | Per-subscriber workflow progress |
| `GET/POST /u/:email_log_id?sig=` | Unsubscribe confirmation page / RFC 8058 one-click POST |
| `GET /health` | Liveness check |
| `POST /api/templates/render` | Render unsaved template content (editor preview) |
| `GET /api/subscribers/fields` | Custom field keys and tags in use (segment builder) |
| `POST /api/subscribers/query` | Paginated search with every filter in a JSON body (see below) |
| `POST /api/subscribers/bulk-action` | `{"action": "add_tag"/"remove_tag"/"set_status"/"delete", "value", "ids": [...]}` or `"filters": {...}` for everyone matching |
| `POST /api/campaigns/audience/preview` | Recipient count + sample for an unsaved audience |
| `POST /api/campaigns/:id/export` | Campaign report: `{"format": "xlsx"}`, or `{"format": "csv", "part": "recipients"/"summary"/"links"}` |
| `DELETE /api/businesses/me` | Delete the account and all its data: `{"password", "confirm": "DELETE"}` |

List endpoints take `?page=&per_page=` (max 100). Dates (`date_from`, `date_to`, `subscribed_from`, ...) are `YYYY-MM-DD` or ISO datetimes; a plain `date_to` includes that whole day.

- **Subscribers** (`GET /api/subscribers` or the `query` body): `search`, `status`, `tag`, `segment_id`, `subscribed_from/to`, `created_from/to`, `engagement_min/max`, `rules` (segment-format rules; JSON in the query string).
- **Campaigns:** `status`, `search` (name or subject), `date_from/to` (send, scheduled or created date).
- **Email logs:** `status`, `campaign_id`, `email`, `subject`, `date_from/to`.
- **Analytics** (`engagement`, `subscriber-growth`): `days`, or `date_from/to`. Errors come back as `{"error": "...", "details": ...}` with a matching HTTP status.

### Segment rules

```json
{"logic": "AND", "rules": [
  {"field": "status", "operator": "equals", "value": "active"},
  {"field": "custom_fields.plan", "operator": "in", "value": ["pro", "team"]},
  {"field": "last_opened_at", "operator": "within_last_days", "value": 30},
  {"field": "tags", "operator": "contains", "value": "vip"},
  {"logic": "OR", "rules": [ ... ]}
]}
```

- **Fields:** subscriber columns, `tags`, `custom_fields.<key>` (an unknown field name is also treated as a custom field), and campaign history (`campaign_received`, `campaign_opened` or `campaign_clicked` combined with `equals` a campaign id).
- **Operators:** `equals`, `not_equals`, `contains`, `not_contains`, `starts_with`, `ends_with`, `greater_than`, `less_than`, `greater_or_equal`, `less_or_equal`, `in`, `not_in`, `is_set`, `is_not_set`, `before`, `after`, `within_last_days`, `not_within_last_days`, `between` (value `[from, to]`; either end may be empty; works for dates and numbers).

Campaigns only ever send to `active` subscribers, whatever the rules say.

### Campaign audiences

Instead of a single `segment_id`, a campaign can take an `audience`. People matching **any** include group receive it; anyone in an exclude group is dropped. With no include group it goes to all active subscribers.

```json
{"audience": {
  "segment_ids": ["..."], "tags": ["vip"], "subscriber_ids": ["..."],
  "rules": {"logic": "AND", "rules": [{"field": "subscribed_at", "operator": "between", "value": ["2026-09-01", "2026-09-30"]}]},
  "exclude_segment_ids": ["..."], "exclude_tags": ["do-not-mail"]
}}
```

### Automation workflows

The format matches the spec. Step types are `send_email` (optional `delay_days`, `delay_hours` or `delay_minutes`), `wait`, `condition`, `add_tag`, `remove_tag`, `update_field` and `unsubscribe`.

- **Conditions:** `email_opened`, `email_not_opened`, `email_clicked` and `email_not_clicked` check the last email the workflow sent. `segment_rules` takes a `"rules": {...}` object.
- **Branching:** `if_true` and `if_false` (and `next` on any step) jump to a step id. `null` continues to the next step, and `"end"` or an unknown id ends the workflow.
- **Triggers:**
  - `new_subscriber` runs once per subscriber.
  - `email_opened` and `email_clicked` accept an optional campaign id as `trigger_value`. An automation is never re-triggered by its own emails.
  - `custom_event` uses `trigger_value` as the event name.
  - `time_based` uses `trigger_value` of the form `days_after_subscribe:N`. It only fires for anniversaries that fall after the automation was created, so creating one does not mail the whole existing list.

## Background jobs

| Job | Schedule |
|---|---|
| Start due scheduled campaigns, then process the email queue | every `QUEUE_PROCESSING_INTERVAL` s |
| Advance automation instances and time-based triggers | 30 s |
| Recalculate campaign counters and engagement scores | 5 min |
| Bounce processing (repeat soft-bouncers, drop mail to inactive subscribers) | 1 h |
| Cleanup past `EMAIL_LOG_RETENTION_DAYS`, full analytics and segment-count refresh | 02:00 UTC |
| Reset daily send counters | 00:00 UTC |

Sending honours each business's daily limit and `MAX_EMAILS_PER_MINUTE`. Mail over either limit is deferred, not dropped.
Soft failures retry with exponential backoff up to `MAX_RETRY_ATTEMPTS`.
A hard bounce marks the subscriber `bounced` straight away. Soft bounces do the same once they reach `MAX_SOFT_BOUNCES`.

## Where this differs from the spec

- **Accounts:** businesses have `account_email`, `password_hash` and `token_version` columns. The spec defines a login but no password field, and `token_version` makes logout and password changes revoke tokens.
- **Extra columns:** `physical_address` on businesses (for the CAN-SPAM footer); tags and engagement counters on subscribers; retry, bounce-type and A/B-variant fields on email logs; and `next_run_at`, `waiting_step` and `history` on automation instances.
- **New `email_events` table:** stores raw open, click and unsubscribe events. Best-performing links and open timing are calculated from it.
- **Email log statuses:** `sending` (claimed by a worker) and `failed` (retries used up without a bounce) were added.
- **Dependency versions:** pins were raised to current patch releases, because the spec's Jinja2 and requests pins have known CVEs. `uuid6` was replaced by the standard-library `uuid4`.
- **Template security:** templates render in a Jinja2 sandbox with HTML autoescaping, because tenants write them.
- **Signed links:** click links carry an HMAC signature, so `/t/click` cannot be used as an open redirect. A GET on an unsubscribe link only shows a confirmation page, so link scanners cannot unsubscribe people.

## Known limitations / next steps

- **Plaintext SMTP passwords:** these are stored as plain text, as in the spec. That's fine for a personal install, but encrypt them at rest before hosting it for others.
- **The mailto unsubscribe address is not processed:** `List-Unsubscribe` advertises both an HTTPS one-click URL and `mailto:unsubscribe@<sender_domain>`. Nothing reads that mailbox yet, so connect it to an inbound handler or drop the mailto part.
- **Per-process API rate limit:** the auth rate limiter lives in memory in each process. Use Redis (e.g. Flask-Limiter) to enforce it across workers.
- **No asynchronous bounces:** the platform only sees bounces that happen during the SMTP session. Bounce notifications that arrive later (via webhook or IMAP) are not handled.
- **No DNS checks:** SPF, DKIM and DMARC verification and IP warm-up are not implemented.
