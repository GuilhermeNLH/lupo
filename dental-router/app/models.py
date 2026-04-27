"""Data models for Dental Router."""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal, Optional


@dataclass
class Destination:
    """A copy destination."""

    id: str
    name: str
    path: str
    enabled: bool = True

    @classmethod
    def new(cls, name: str, path: str) -> "Destination":
        return cls(id=str(uuid.uuid4()), name=name, path=path)


MatchType = Literal["contains", "startswith", "endswith", "regex"]


@dataclass
class Rule:
    """A routing rule."""

    id: str
    name: str
    pattern: str
    match_type: MatchType
    case_sensitive: bool
    priority: int
    destination_id: str
    enabled: bool = True

    @classmethod
    def new(
        cls,
        name: str,
        pattern: str,
        match_type: MatchType,
        case_sensitive: bool,
        priority: int,
        destination_id: str,
    ) -> "Rule":
        return cls(
            id=str(uuid.uuid4()),
            name=name,
            pattern=pattern,
            match_type=match_type,
            case_sensitive=case_sensitive,
            priority=priority,
            destination_id=destination_id,
        )


ItemStatus = Literal["pending", "copied", "error", "ignored", "conflict", "no_match"]
ItemType = Literal["file", "folder"]


@dataclass
class DetectedItem:
    """An item detected in the source directory."""

    id: str
    name: str
    path: str
    item_type: ItemType
    rule_applied: Optional[str] = None
    destination_id: Optional[str] = None
    destination_name: Optional[str] = None
    status: ItemStatus = "pending"
    timestamp: datetime = field(default_factory=datetime.now)
    error_msg: Optional[str] = None

    @classmethod
    def new(cls, name: str, path: str, item_type: ItemType) -> "DetectedItem":
        return cls(id=str(uuid.uuid4()), name=name, path=path, item_type=item_type)


@dataclass
class AppSettings:
    """Global application settings."""

    source_dir: str = ""
    quarantine_dir: str = ""
    auto_mode: bool = False
    on_no_match: Literal["manual", "quarantine"] = "manual"
    on_conflict: Literal["manual", "quarantine"] = "manual"
    scan_debounce_seconds: float = 2.0
    destinations: list[Destination] = field(default_factory=list)
    rules: list[Rule] = field(default_factory=list)
