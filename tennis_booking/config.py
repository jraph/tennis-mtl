from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any


DATA_DIR = Path("data")
CONFIG_PATH = DATA_DIR / "config.json"
LOCATIONS_PATH = DATA_DIR / "locations.json"
DEFAULT_BOROUGH_IDS = ["7", "5"]
DEFAULT_FACILITY_TYPE_IDS = ["175", "115"]
DEFAULT_TIME_CHOICES = [
    "08:00",
    "09:00",
    "10:00",
    "11:00",
    "12:00",
    "13:00",
    "14:00",
    "15:00",
    "16:00",
    "17:00",
    "18:00",
    "19:00",
    "20:00",
    "21:00",
]


@dataclass
class AppConfig:
    date: str = field(default_factory=lambda: (date.today() + timedelta(days=2)).isoformat())
    time: str = field(default_factory=lambda: current_time_slot())
    time_window_hours: int = 1
    scan_window_hours: int = 24
    check_days: int = 1
    check_dates: list[str] = field(default_factory=list)
    check_times: list[str] = field(default_factory=lambda: [current_time_slot()])
    borough_ids: list[str] = field(default_factory=lambda: DEFAULT_BOROUGH_IDS.copy())
    facility_type_ids: list[str] = field(default_factory=lambda: DEFAULT_FACILITY_TYPE_IDS.copy())
    site_ids: list[str] = field(default_factory=list)
    site_names: list[str] = field(default_factory=list)
    sort_column: str = "facility.name"
    open_when_found: bool = False

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AppConfig":
        config = cls()
        uses_legacy_scan_defaults = "check_days" not in data and "check_times" not in data
        for key in asdict(config):
            if key in data:
                setattr(config, key, data[key])

        if "scan_days" in data and "scan_window_hours" not in data:
            config.scan_window_hours = int(data["scan_days"]) * 24
        if uses_legacy_scan_defaults:
            config.time_window_hours = 1
            config.scan_window_hours = 72

        config.time_window_hours = clamp_int(config.time_window_hours, 1, 12)
        config.scan_window_hours = clamp_int(config.scan_window_hours, 1, 336)
        config.check_days = clamp_int(config.check_days, 1, 14)
        config.borough_ids = [str(item) for item in config.borough_ids if str(item)]
        config.facility_type_ids = [str(item) for item in config.facility_type_ids if str(item)]
        config.site_ids = [str(item) for item in config.site_ids if str(item)]
        config.site_names = [str(item) for item in config.site_names if str(item)]
        config.check_dates = normalize_dates(config.check_dates)
        config.check_times = normalize_times(config.check_times)
        config.date = normalize_date(config.date)
        return config

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        return minimum
    return min(max(number, minimum), maximum)


def normalize_times(values: Any) -> list[str]:
    if isinstance(values, str):
        raw_values = values.split(",")
    elif isinstance(values, list):
        raw_values = values
    else:
        raw_values = [current_time_slot()]

    normalized = []
    for value in raw_values:
        text = str(value).strip()
        try:
            hour, minute = [int(part) for part in text.split(":", 1)]
        except (ValueError, AttributeError):
            continue
        if 0 <= hour <= 23 and 0 <= minute <= 59:
            normalized.append(f"{hour:02d}:{minute:02d}")

    return normalized or [current_time_slot()]


def normalize_date(value: Any) -> str:
    target = date.today() + timedelta(days=2)
    try:
        parsed = date.fromisoformat(str(value))
    except ValueError:
        return target.isoformat()
    if parsed < target:
        return target.isoformat()
    return parsed.isoformat()


def normalize_dates(values: Any) -> list[str]:
    if not isinstance(values, list):
        return []
    normalized = []
    target = date.today()
    for value in values:
        try:
            parsed = date.fromisoformat(str(value))
        except ValueError:
            continue
        if parsed >= target:
            normalized.append(parsed.isoformat())
    return sorted(set(normalized))


def default_target_date() -> str:
    return (date.today() + timedelta(days=2)).isoformat()


def current_time_slot() -> str:
    now = datetime.now()
    return f"{now.hour:02d}:00"


def load_config() -> AppConfig:
    if not CONFIG_PATH.exists():
        return AppConfig()

    try:
        return AppConfig.from_dict(json.loads(CONFIG_PATH.read_text(encoding="utf-8")))
    except (OSError, json.JSONDecodeError):
        return AppConfig()


def save_config(config: AppConfig) -> None:
    DATA_DIR.mkdir(exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(config.to_dict(), indent=2), encoding="utf-8")


def load_locations() -> dict[str, Any]:
    try:
        data = json.loads(LOCATIONS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        data = {}

    return {
        "boroughs": data.get("boroughs") if isinstance(data.get("boroughs"), list) else [],
        "sites": data.get("sites") if isinstance(data.get("sites"), list) else [],
    }
