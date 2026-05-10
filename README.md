# Tennis Court Booker

Flask web app that checks [Loisirs Montréal](https://loisirs.montreal.ca) tennis court availability and links directly to the official booking page when a slot opens up.

Calls the public Loisirs Montréal search API (no login required). Background scheduled checks run inside the web process via APScheduler so you can leave the app running and come back to results.

## Features

- **Availability grid** — pick one or more dates and times, see all matching slots across boroughs in one view
- **Location filters** — toggle by named park (La Fontaine, Jeanne-Mance, Beaubien, Claude-Robillard, etc.)
- **Direct booking links** — each result links to the exact Loisirs Montréal booking page for that court and time slot
- **Auto-open** — optionally open the booking page in the browser the moment a reservable slot appears
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

To use a different port:

```powershell
python app.py --port 5001
```

Then open:

```
http://127.0.0.1:5000
```

## Run one check (CLI)

```powershell
.\.venv\Scripts\Activate.ps1
python -m tennis_booking.check_once
```

Prints available slots and direct booking URLs to stdout.

## Configuration

Settings are stored in `data/config.json` and editable via the web UI (Save defaults button) or directly.

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
| `open_when_found` | `false` | Auto-open the booking page when a reservable slot is found |

## Raspberry Pi deployment

The app runs under Gunicorn managed by systemd. One worker is enough — the scheduler is in-process and concurrent check requests are fast.

**Note:** this exposes the app with no authentication. Make sure port 5000 is not open to the public internet.

```bash
# On the Pi
git clone https://github.com/jraph/tennis-mtl.git
cd tennis-mtl
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp data/config.example.json data/config.json
```

Install and enable the systemd service:

```bash
sed "s|TENNIS_MTL_DIR|$(pwd)|g" scripts/tennis-mtl.service | sed "/\[Service\]/a User=$(whoami)" | sudo tee /etc/systemd/system/tennis-mtl.service > /dev/null
sudo systemctl daemon-reload
sudo systemctl enable --now tennis-mtl
```

Check it's running:

```bash
sudo systemctl status tennis-mtl
journalctl -u tennis-mtl -f
```

The app listens on port 5000 on all interfaces.

## Windows scheduled task

Edit `scripts\run-check.ps1` if you want different defaults, then create a Windows scheduled task that runs:

```powershell
powershell.exe -ExecutionPolicy Bypass -File C:\path\to\tennis\scripts\run-check.ps1
```

Many Montréal courts open reservations 24–48 hours ahead, so schedule the task a minute or two before your target release time.
