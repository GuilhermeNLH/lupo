"""Rule-evaluation engine."""
from __future__ import annotations

import re
from typing import Optional

from app.logger import logger
from app.models import AppSettings, Destination, DetectedItem, Rule


def _matches(rule: Rule, name: str) -> bool:
    """Return True if *name* matches *rule*."""
    if rule.match_type == "regex":
        flags = 0 if rule.case_sensitive else re.IGNORECASE
        try:
            return bool(re.search(rule.pattern, name, flags))
        except re.error as exc:
            logger.error(f"Invalid regex in rule {rule.name!r}: {exc}")
            return False

    haystack = name if rule.case_sensitive else name.lower()
    needle = rule.pattern if rule.case_sensitive else rule.pattern.lower()

    if rule.match_type == "contains":
        return needle in haystack
    if rule.match_type == "startswith":
        return haystack.startswith(needle)
    if rule.match_type == "endswith":
        return haystack.endswith(needle)

    logger.warning(f"Unknown match_type {rule.match_type!r} in rule {rule.name!r}")
    return False


def route_item(
    item: DetectedItem,
    settings: AppSettings,
) -> tuple[str, Optional[str], Optional[str]]:
    """
    Evaluate routing rules for *item*.

    Returns
    -------
    (status, destination_id, rule_name)

    * status ``"ok"``       – exactly one rule matched at top priority
    * status ``"conflict"`` – multiple rules matched at the same top priority
    * status ``"no_match"`` – no rule matched
    """
    active_rules: list[Rule] = [r for r in settings.rules if r.enabled]
    matching: list[Rule] = [r for r in active_rules if _matches(r, item.name)]

    if not matching:
        return ("no_match", None, None)

    # Sort ascending – lower integer = higher priority
    matching.sort(key=lambda r: r.priority)
    top_priority = matching[0].priority
    top_group = [r for r in matching if r.priority == top_priority]

    if len(top_group) > 1:
        return ("conflict", None, None)

    rule = top_group[0]
    return ("ok", rule.destination_id, rule.name)


def get_destination(dest_id: str, settings: AppSettings) -> Optional[Destination]:
    """Return the enabled Destination with *dest_id*, or None."""
    for d in settings.destinations:
        if d.id == dest_id and d.enabled:
            return d
    return None
