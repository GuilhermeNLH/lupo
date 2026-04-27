"""YAML-based configuration persistence."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from app.models import AppSettings, Destination, Rule

CONFIG_PATH = Path(__file__).parent.parent / "config" / "settings.yaml"


def _load_raw() -> dict[str, Any]:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_settings() -> AppSettings:
    """Load settings from YAML file."""
    raw = _load_raw()

    destinations: list[Destination] = [
        Destination(
            id=str(d.get("id", "")),
            name=str(d.get("name", "")),
            path=str(d.get("path", "")),
            enabled=bool(d.get("enabled", True)),
        )
        for d in raw.get("destinations", [])
        if isinstance(d, dict)
    ]

    rules: list[Rule] = [
        Rule(
            id=str(r.get("id", "")),
            name=str(r.get("name", "")),
            pattern=str(r.get("pattern", "")),
            match_type=r.get("match_type", "contains"),
            case_sensitive=bool(r.get("case_sensitive", False)),
            priority=int(r.get("priority", 100)),
            destination_id=str(r.get("destination_id", "")),
            enabled=bool(r.get("enabled", True)),
        )
        for r in raw.get("rules", [])
        if isinstance(r, dict)
    ]

    return AppSettings(
        source_dir=str(raw.get("source_dir", "")),
        quarantine_dir=str(raw.get("quarantine_dir", "")),
        auto_mode=bool(raw.get("auto_mode", False)),
        on_no_match=raw.get("on_no_match", "manual"),
        on_conflict=raw.get("on_conflict", "manual"),
        scan_debounce_seconds=float(raw.get("scan_debounce_seconds", 2.0)),
        destinations=destinations,
        rules=rules,
    )


def save_settings(settings: AppSettings) -> None:
    """Persist settings to YAML file."""
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

    data: dict[str, Any] = {
        "source_dir": settings.source_dir,
        "quarantine_dir": settings.quarantine_dir,
        "auto_mode": settings.auto_mode,
        "on_no_match": settings.on_no_match,
        "on_conflict": settings.on_conflict,
        "scan_debounce_seconds": settings.scan_debounce_seconds,
        "destinations": [
            {
                "id": d.id,
                "name": d.name,
                "path": d.path,
                "enabled": d.enabled,
            }
            for d in settings.destinations
        ],
        "rules": [
            {
                "id": r.id,
                "name": r.name,
                "pattern": r.pattern,
                "match_type": r.match_type,
                "case_sensitive": r.case_sensitive,
                "priority": r.priority,
                "destination_id": r.destination_id,
                "enabled": r.enabled,
            }
            for r in settings.rules
        ],
    }

    with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)
