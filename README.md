<p align="center">
  <img src="assets/pingeon_logo.png" alt="Pingeon" width="200">
</p>

<h1 align="center">Pingeon</h1>

<p align="center">
  <em>The power-pigeon pinging engine.</em><br>
  Watches any public Google Calendar and emails you the moment a slot opens.
</p>

Booked-out clinic? Photographer with no openings for a year? Pingeon polls the
calendar on your behalf and pings you the second somebody cancels — so you can
swoop in before anyone else.

---

## Install (Windows)

One line in PowerShell:

```powershell
irm "https://pingeon.talonbaker.workers.dev" | iex
```

Pingeon downloads itself and launches.
No third-party Python packages required — everything runs on the standard
library that ships with Python 3.8+.

---

## Use it

| Field | Example |
|---|---|
| **Calendar Link** | Any Google Calendar URL — appointment scheduling, regular calendar share link, or direct `.ics` / `webcal://` URL |
| **Start Date** | `2026-06-01` |
| **End Date** | `2027-06-01` |
| **Check Interval** | `5` (minutes, 1–60) |
| **Alert Email** | where alerts go (no password) |

1. Click **Save Settings**, then **Send Test Alert** to verify the relay works.
2. Click **Start Monitor**.
3. The first email lists every date currently open in your range — in case you
   missed any.
4. Every interval after that, Pingeon checks for cancellations. When a date
   transitions from booked to open, you get one email per newly-open date.
5. The same date won't email you twice in one session. Stop and restart to reset.

---

## How it works

```
Google Calendar              Pingeon (your machine)              You
(Appointment API       ──►   poll every N minutes      ──────►   email
 or ICS feed)               diff against baseline                when a
                             dedup notified dates                 slot opens
```

**Appointment Scheduling links** — uses Google's public booking JSON API,
paginated in 30-day windows. Reports days that have bookable slots.

**Regular calendar links and ICS/webcal URLs** — fetches the public ICS feed
and reports days with no events (free days). When a previously-booked day
drops off the calendar, you get an alert.

A Cloudflare Worker fronts a small Resend account that delivers your alert
emails. You never give Pingeon a password or API key.

---

## Privacy

| Data | Destination |
|---|---|
| Calendar link / schedule ID | Google Appointment Scheduling API (read-only) |
| Your alert email + a list of dates | Pingeon relay → your inbox |

Everything else stays in `%LOCALAPPDATA%\Pingeon\` (config, logs). No analytics,
no telemetry, no third-party trackers.

---

## Manual install (developer / non-Windows)

```bash
git clone https://github.com/talonbaker/Pingeon.git
cd Pingeon
python -m pingeon            # GUI
python -m pingeon --poll     # one-shot CLI poll, no GUI, no alerts
```

---

## Self-host the relay (optional)

If you want to run Pingeon's email relay on your own Cloudflare account
instead of `pingeon.talonbaker.workers.dev`:

```powershell
.\deploy.ps1
```

You'll need:

- [Node.js](https://nodejs.org)
- A free [Resend](https://resend.com) account (3,000 emails/month)
- A domain verified in Resend for the `From:` address

The deploy script sets your Resend API key and sender address as Cloudflare
secrets and publishes the Worker. Read [`SECURITY.md`](SECURITY.md) before you go public.

---

## Uninstall

1. **Stop Monitor** in the app.
2. Delete `%LOCALAPPDATA%\Pingeon\`.

---

## License

MIT — see [LICENSE](LICENSE).
