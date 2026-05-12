# Tennis Court Booker

Flask web app that checks [Loisirs Montréal](https://loisirs.montreal.ca) tennis court availability and links directly to the official booking page when a slot opens up.

Calls the public Loisirs Montréal search API (no login required). Press **Check now** to run a query; results are returned over a streaming response so you see progress as it goes.

## Features

- **Availability grid** — pick one or more dates and times, see all matching slots across boroughs in one view
- **Location filters** — toggle by named park (La Fontaine, Jeanne-Mance, Beaubien, Claude-Robillard, etc.)
- **Direct booking links** — each result links to the exact Loisirs Montréal booking page for that court and time slot
- **CLI mode** — run a single check from the terminal without starting the web server

## Setup

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Copy the example config (the web UI can update it at runtime):

```powershell
Copy-Item data\config.example.json data\config.json
```

`playwright` and `playwright install chromium` are only needed if you use `tennis_booking/inspect_network.py` (a dev tool for inspecting raw API responses). Install it separately with `pip install playwright` in that case.

## Run the web app

```powershell
.\.venv\Scripts\Activate.ps1
python app.py
```

Then open:

```
https://127.0.0.1:5000
```

(The dev server uses an adhoc self-signed cert — your browser will show a one-time warning. Pass `--no-https` to disable, or `--port 5001` to listen on a different port.)

## Run one check (CLI)

```powershell
.\.venv\Scripts\Activate.ps1
python -m tennis_booking.check_once
```

Prints available slots and direct booking URLs to stdout.

## Configuration

Server-side seed defaults live in `data/config.json`. The web UI lets each browser override them via the **Save defaults** button — those overrides are kept in `localStorage` on the device, so they don't affect other clients.

| Field | Default | Description |
|---|---|---|
| `check_dates` | `[]` | Specific dates to check (overrides `check_days`) |
| `check_days` | `1` | Number of days starting from `date` |
| `date` | today + 2 | First date to check |
| `check_times` | current hour | Time slots to check (list of `HH:MM`) |
| `time_window_hours` | `1` | Hour window after each check time |
| `borough_ids` | `["7","5"]` | Loisirs borough IDs to search |
| `facility_type_ids` | `["175","115"]` | Facility type IDs (175 = outdoor hard, 115 = outdoor clay) |
| `site_names` | `[]` | Filter to specific park names (partial, case-insensitive) |

## Raspberry Pi deployment

The app runs under Gunicorn managed by systemd. One worker is enough — checks are on-demand and fast.

**Note:** this exposes the app with no authentication. Make sure port 5000 is not open to the public internet.

```bash
# On the Pi
git clone https://github.com/jraph/tennis-mtl.git
cd tennis-mtl
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp data/config.example.json data/config.json
```

Install and enable the systemd service (idempotent — re-run after pulling unit changes):

```bash
bash scripts/install-service.sh
sudo systemctl enable tennis-mtl
```

The script substitutes the install path, writes `/etc/systemd/system/tennis-mtl.service`, reloads systemd, restarts the service, and prints status. On first start it generates a self-signed `cert.pem` / `key.pem` in the repo root via `scripts/ensure_cert.py`.

Check it's running:

```bash
sudo systemctl status tennis-mtl
journalctl -u tennis-mtl -f
```

The app listens on `https://0.0.0.0:5000` (self-signed cert; browsers will show a one-time warning).

## Windows scheduled task

Edit `scripts\run-check.ps1` if you want different defaults, then create a Windows scheduled task that runs:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\path\to\tennis\scripts\run-check.ps1
```

Many Montréal courts open reservations 24–48 hours ahead, so schedule the task a minute or two before your target release time.
