# Pingeon
## The Power Pigeon Pinging Engine
Pingeon is an automated calendar monitoring system that watches public calendars for availability and alerts you the instant an opening appears. No more manual checking, no more missing out -- Pingeon swoops in and notifies you immediately when a slot becomes available. Whether you're hunting for a photographer appointment, booking a vacation rental, or catching a limited-availability event, Pingeon gives you the speed advantage to claim it first.

Set it. Forget it. Get pinged.

---

## Install (Windows)

```powershell
irm "https://pingeon.talonbaker.workers.dev" | iex
```

That's it. Pingeon downloads itself, installs its dependency, and puts a shortcut on your Desktop.

---

## How it works

1. Reads any **public** Google Calendar ICS feed -- no login, no API key
2. Compares each check against the previous snapshot
3. When a booked slot disappears (cancellation / opening), Pingeon emails you
4. Repeats on the interval you choose (default: every 2 minutes)

---

## Configuration

| Field | Example |
|---|---|
| Calendar Link | Share URL from Google Calendar |
| Start Date | `2027-01-15` |
| End Date | `2027-03-31` |
| Check Interval | `2` (minutes, 1-60) |
| Alert Email | `you@example.com` (where alerts go) |

No password required. Pingeon's relay handles the sending.

---

## Privacy

| What leaves your machine | Where |
|---|---|
| Public calendar ID | Google Calendar ICS feed (read-only) |
| Your email + slot info | Pingeon relay -> your inbox |

Everything else stays local (`%LOCALAPPDATA%\Pingeon\`). No analytics, no telemetry.

---

## Manual setup

```powershell
git clone https://github.com/talonbaker/Pingeon.git
cd Pingeon
pip install -r requirements.txt
python -m pingeon
```

CLI poll (no GUI): `python -m pingeon --poll`

---

## Deploy the Worker (one-time, developer only)

Requires [Node.js](https://nodejs.org) and a free [Resend](https://resend.com) account (3,000 emails/month).

```powershell
.\deploy.ps1
```

That's it -- no directory changes, no manual wrangler commands.

---

## Uninstall

1. Click **Stop Monitor** in the app
2. Delete `%LOCALAPPDATA%\Pingeon\`
3. Delete the `Pingeon` shortcut from your Desktop

---

## License

MIT -- see [LICENSE](LICENSE)
