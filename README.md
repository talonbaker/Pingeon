# Pingeon — Photographer Availability Monitor

Monitors a **public** Google Calendar for cancellations and emails you the moment a slot opens in your desired date range.

---

## Quick Install (Windows)

```powershell
irm "https://raw.githubusercontent.com/<user>/Pingeon/main/setup.ps1" | iex
```

This installs the app, installs Python dependencies, and puts a shortcut on your Desktop. Nothing else.

---

## What it does

1. Reads the photographer's **public** Google Calendar ICS feed (no login required)
2. Compares each check against the previous state
3. When a booked slot disappears (cancellation), sends you an email via Gmail SMTP
4. Repeats on the interval you choose (default: every 2 minutes)

---

## Privacy & Security

| Where data goes | What leaves your machine |
|---|---|
| Google Calendar ICS feed | Only the public calendar ID in the URL |
| Gmail SMTP (`smtp.gmail.com:587`) | The alert email to your own address |

**Everything else stays local:**
- Your email address → saved in `config.json` on your machine
- Your Gmail password → **never saved**, entered once per session, kept in memory only
- Calendar link → saved locally
- Date ranges → saved locally
- All logs → saved locally in `monitor.log`

No analytics. No telemetry. No cloud storage. No third-party servers.

---

## Manual Setup (if you prefer)

```powershell
# 1. Clone the repo
git clone https://github.com/<user>/Pingeon.git
cd Pingeon

# 2. Install dependencies
pip install -r requirements.txt

# 3. Launch
python -m photographer_monitor
```

---

## Configuration

Fill in the GUI fields on first launch:

| Field | Example |
|---|---|
| Calendar Link | The share link from Google Calendar |
| Start Date | `2027-01-15` |
| End Date | `2027-03-31` |
| Email Address | `you@gmail.com` |
| Check Interval | `2` (minutes) |

Click **Save Settings**, then **Start Monitor**. You will be asked for your Gmail password — it is used only for SMTP and is not saved.

### Gmail App Password

If you use 2-Step Verification (recommended), generate an **App Password**:

1. Go to your Google Account → Security → 2-Step Verification → App passwords
2. Generate a password for "Mail" / "Windows Computer"
3. Use that 16-character password in the monitor

---

## Files & Locations

```
C:\Users\<you>\AppData\Local\PhotographerMonitor\
  config.json    — your settings (no passwords)
  monitor.log    — rolling log file (10 MB max, 5 backups)
  state.db       — SQLite snapshot of last-seen calendar events
```

---

## CLI Usage

```powershell
# Run one poll cycle (no GUI, no email — useful for testing)
python -m photographer_monitor --poll
```

---

## Uninstall

1. Click **Stop Monitor** in the GUI (if running)
2. Delete `C:\Users\<you>\AppData\Local\PhotographerMonitor\`
3. Delete the Desktop shortcut
4. Optionally: `pip uninstall icalendar requests`

---

## License

MIT — see [LICENSE](LICENSE)
# Pingeon
## The Power Pigeon Pinging Engine
Pingeon is an automated calendar monitoring system that watches public calendars for availability and alerts you the instant an opening appears. No more manual checking, no more missing out—Pingeon swoops in and notifies you immediately when a slot becomes available. Whether you're hunting for a photographer appointment, booking a vacation rental, or catching a limited-availability event, Pingeon gives you the speed advantage to claim it first.
Set it. Forget it. Get pinged.
