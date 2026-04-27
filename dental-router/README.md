# Dental Router

A Python desktop application for **routing (copying) files and folders** from a watched source directory to multiple destinations, based on fully configurable name-matching rules.

---

## Features

- **Non-destructive**: files are always **copied**, never moved.
- **Live monitoring** with `watchdog` – reacts to new files and folders.
- **Rule engine**: `contains`, `startswith`, `endswith`, `regex` matchers with priority, case-sensitivity toggle, and per-rule enable/disable.
- **Conflict handling**: when multiple rules tie on priority the item is flagged for manual review (or sent to quarantine).
- **Auto mode**: copy automatically on a single rule match, or wait for manual confirmation.
- **No-overwrite policy**: if the target already exists the app appends ` (1)`, ` (2)` … to the filename.
- **File stability check**: waits until an incoming file stops growing before copying (safe for network drives).
- **GUI**: dark-themed `customtkinter` interface with four tabs – Settings, Destinations, Rules, Monitor.
- **YAML config**: human-readable `config/settings.yaml` that can be edited manually or via the GUI.
- **Rotating logs**: stored in `logs/dental_router.log` (5 MB × 3 backups).

---

## Requirements

- Python 3.11 or newer
- Windows (tested), macOS / Linux (should work)

---

## Installation

```bash
# 1. Clone / download the project
cd dental-router

# 2. Create a virtual environment
python -m venv .venv

# 3. Activate it
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Windows CMD:
.venv\Scripts\activate.bat
# macOS / Linux:
source .venv/bin/activate

# 4. Install dependencies
pip install -r requirements.txt
```

---

## Running

```bash
python app/main.py
```

Or, from the project root:

```bash
python -m app.main
```

---

## Configuration

### Via the GUI

1. **⚙ Settings tab** – set the Source directory, Quarantine directory, auto-mode, and conflict/no-match behaviour.
2. **📁 Destinations tab** – add the target folders (e.g. `E3_01`, `E3_02`).
3. **📋 Rules tab** – add name-matching rules; each rule links a pattern to a destination.
4. Click **💾 Save Settings** in the Settings tab to persist changes to `config/settings.yaml`.

### Manually editing `config/settings.yaml`

```yaml
source_dir: "D:/incoming"
quarantine_dir: "D:/quarantine"
auto_mode: true           # true = copy automatically; false = suggest only
on_no_match: quarantine   # manual | quarantine
on_conflict: manual       # manual | quarantine
scan_debounce_seconds: 2.0

destinations:
  - id: dest-e3-01
    name: "E3_01"
    path: "D:/destino/E3_01"
    enabled: true

rules:
  - id: rule-e3-01
    name: "E3_01 files"
    pattern: "E3_01"
    match_type: contains    # contains | startswith | endswith | regex
    case_sensitive: false
    priority: 10            # lower = higher priority
    destination_id: dest-e3-01
    enabled: true
```

---

## Practical rule examples

| Goal | match_type | pattern | case_sensitive | priority |
|------|-----------|---------|---------------|----------|
| Files whose name contains `"E3_01"` | `contains` | `E3_01` | `false` | `10` |
| Files starting with `"RX_"` | `startswith` | `RX_` | `true` | `20` |
| Files ending with `.dcm` | `endswith` | `.dcm` | `false` | `30` |
| Files matching pattern `^\d{6}_` | `regex` | `^\d{6}_` | `false` | `5` |

---

## Monitor tab – per-item actions

| Button | Action |
|--------|--------|
| **Copy to…** | Open a dialog to manually pick a destination and copy immediately. |
| **Auto-rule** | Re-evaluate rules and copy to the matched destination. |
| **Ignore** | Mark the item as ignored (no copy). |

---

## Troubleshooting

### Permission denied
- Make sure the current user has **read** access to the source directory and **write** access to all destinations.
- On Windows, run as Administrator if accessing a mapped network drive.

### Network / mapped drive not monitored
- `watchdog` may not fire events reliably for some network protocols (SMB, NFS).  
  Increase `scan_debounce_seconds` to a higher value (e.g. `5`).
- Ensure the network drive is mounted **before** clicking Start.

### File is locked / being written
- The copier waits up to 30 seconds for the file to stabilise (size stops changing) before copying.  
  If the file is still locked after 30 s it will be copied anyway – errors are logged.

### Invalid regex
- A rule with `match_type: regex` and a malformed pattern is skipped silently and an error is written to the log.  
  Check `logs/dental_router.log` for details.

### Application won't start
1. Confirm Python ≥ 3.11: `python --version`.
2. Confirm the venv is activated and `pip install -r requirements.txt` completed without errors.
3. On Linux/macOS, `customtkinter` requires Tk – install `python3-tk` via your package manager.

---

## Building a Windows executable (.exe)

```bash
pip install pyinstaller

pyinstaller \
  --onefile \
  --windowed \
  --name "DentalRouter" \
  --add-data "config;config" \
  --add-data "logs;logs" \
  app/main.py
```

The resulting `dist/DentalRouter.exe` is a self-contained executable.  
Copy `config/settings.yaml` next to the `.exe` before distributing (or let the first run create it).

> **Note**: on Windows, use `;` as the separator in `--add-data`; on macOS/Linux use `:`.

---

## Project structure

```
dental-router/
├── app/
│   ├── main.py        Entry point
│   ├── gui.py         CustomTkinter GUI (4 tabs)
│   ├── watcher.py     Watchdog-based directory monitor
│   ├── router.py      Rule-evaluation engine
│   ├── copier.py      Robust file/folder copy
│   ├── models.py      Data classes (Destination, Rule, DetectedItem, AppSettings)
│   ├── config.py      YAML load / save
│   └── logger.py      Rotating-file + console logger
├── config/
│   └── settings.yaml  Runtime configuration
├── logs/              Log files (auto-created)
├── requirements.txt
└── README.md
```
