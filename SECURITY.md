# Security model

Pingeon is a desktop monitor talking to two networks:

1. **Google Appointment Scheduling API** — read-only, public, no credentials.
2. **The Pingeon Cloudflare Worker** — receives "send this email to me" requests
   and forwards them through Resend.

This document describes the threat model and the protections in place. Read
this before self-hosting the Worker.

## Trust boundaries

- Pingeon never sees your Google account or any password.
- Pingeon never sees your Resend API key — it lives only in Cloudflare secrets.
- Pingeon stores the user's chosen alert-email address in plaintext at
  `%LOCALAPPDATA%\Pingeon\config.json`. Treat it like any other config file.

## The relay (`/notify`) — what stops abuse

The relay is the most attack-able component because it can send email on your
domain's behalf. The fundamental constraint: the same `NOTIFY_TOKEN` is shared
with every user of the install one-liner, so the token is best treated as
*"slows down casual abuse"* rather than secure auth.

Layered defenses (in `cloudflare/worker.js`):

| Layer | What it does |
|---|---|
| Bearer token | Rejects unauthenticated requests |
| Per-IP rate limit | 30 req/min via Cloudflare's ratelimit binding |
| Per-recipient rate limit | 20 emails/hour to any single address |
| Body size cap | 16 KB max request body |
| `to` regex | Strict email format, ≤254 chars, no quotes/control chars |
| `slots[].date` regex | Each date must match `YYYY-MM-DD` |
| `slots` count cap | Max 100 dates per request |
| `kind` whitelist | `initial` or `update`; anything else falls back to `update` |
| Subject whitelist | Email subjects come from a fixed set, never user input |
| Body templates | Email bodies are templated; the only attacker-influenced text is the validated date strings |
| Error opacity | Resend's response is never proxied back to the caller |

Even if the token leaks, the attacker can:

- Send up to 30 emails/minute total from one IP, capped at 20/hour to any
  single recipient.
- Only send dates (no free-text body content).
- Only send to addresses they already know.

That is significantly harder to weaponize than an open relay, but it is not
zero. **If you self-host, monitor your Resend usage.** Rotate `NOTIFY_TOKEN`
(re-run `deploy.ps1`) if you see abuse.

## Other surfaces

**`extract_calendar_id` / SSRF** — `pingeon/config.py` follows redirects only
when the user-supplied URL has hostname `calendar.app.google` (parsed, not
substring match). Any other hostname is parsed locally without network calls.

**`irm | iex` install** — the `setup.ps1` script is fetched from the Worker on
every install. The Worker pulls it from `raw.githubusercontent.com` at the
pinned `main` branch. If you don't trust GitHub or the Worker host, do a
manual install from a tagged release instead.

**Token injection in `setup.ps1`** — the Worker base64-validates `NOTIFY_TOKEN`
before injecting it into the served script, so it cannot break out of the
single-quoted PowerShell literal.

## Reporting

If you find a vulnerability, open a private security advisory on GitHub or
email the address listed on [talonbaker.com](https://talonbaker.com).
