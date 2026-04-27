"""
Dental Router – CustomTkinter GUI
==================================
Tabs
----
1. Settings   – source/quarantine dirs, global options
2. Destinations – manage copy destinations
3. Rules        – manage routing rules
4. Monitor      – live detected-items table with per-row actions
"""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog
from typing import Literal, Optional, cast

import customtkinter as ctk

from app.config import load_settings, save_settings
from app.copier import copy_item
from app.logger import logger
from app.models import AppSettings, DetectedItem, Destination, MatchType, Rule
from app.router import get_destination, route_item
from app.watcher import Watcher

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_STATUS_COLORS: dict[str, str] = {
    "pending":    "#FFA500",
    "copied":     "#2ECC71",
    "error":      "#E74C3C",
    "ignored":    "#7F8C8D",
    "conflict":   "#E67E22",
    "no_match":   "#9B59B6",
}

_MATCH_TYPES = ["contains", "startswith", "endswith", "regex"]


def _browse_dir(var: ctk.StringVar) -> None:
    path = filedialog.askdirectory()
    if path:
        var.set(path)


# ──────────────────────────────────────────────────────────────────────────────
# Dialog: Add / Edit Destination
# ──────────────────────────────────────────────────────────────────────────────

class DestinationDialog(ctk.CTkToplevel):
    def __init__(self, parent: ctk.CTk, dest: Optional[Destination] = None) -> None:
        super().__init__(parent)
        self.title("Destination" if dest is None else "Edit Destination")
        self.geometry("480x200")
        self.grab_set()
        self.resizable(False, False)

        self.result: Optional[Destination] = None

        self._name_var = ctk.StringVar(value=dest.name if dest else "")
        self._path_var = ctk.StringVar(value=dest.path if dest else "")
        self._enabled_var = ctk.BooleanVar(value=dest.enabled if dest else True)

        ctk.CTkLabel(self, text="Name:").grid(row=0, column=0, padx=12, pady=8, sticky="e")
        ctk.CTkEntry(self, textvariable=self._name_var, width=280).grid(row=0, column=1, padx=4, pady=8, columnspan=2, sticky="w")

        ctk.CTkLabel(self, text="Path:").grid(row=1, column=0, padx=12, pady=8, sticky="e")
        ctk.CTkEntry(self, textvariable=self._path_var, width=220).grid(row=1, column=1, padx=4, pady=8, sticky="w")
        ctk.CTkButton(self, text="Browse", width=60, command=lambda: _browse_dir(self._path_var)).grid(row=1, column=2, padx=4)

        ctk.CTkLabel(self, text="Enabled:").grid(row=2, column=0, padx=12, pady=4, sticky="e")
        ctk.CTkCheckBox(self, text="", variable=self._enabled_var).grid(row=2, column=1, padx=4, sticky="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=3, column=0, columnspan=3, pady=10)
        ctk.CTkButton(btn_frame, text="Save", command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy, fg_color="gray40").pack(side="left", padx=8)

    def _save(self) -> None:
        name = self._name_var.get().strip()
        path = self._path_var.get().strip()
        if not name or not path:
            messagebox.showwarning("Validation", "Name and Path are required.", parent=self)
            return
        self.result = Destination.new(name, path)
        self.result.enabled = self._enabled_var.get()
        self.destroy()


# ──────────────────────────────────────────────────────────────────────────────
# Dialog: Add / Edit Rule
# ──────────────────────────────────────────────────────────────────────────────

class RuleDialog(ctk.CTkToplevel):
    def __init__(
        self,
        parent: ctk.CTk,
        destinations: list[Destination],
        rule: Optional[Rule] = None,
    ) -> None:
        super().__init__(parent)
        self.title("Rule" if rule is None else "Edit Rule")
        self.geometry("520x320")
        self.grab_set()
        self.resizable(False, False)

        self.result: Optional[Rule] = None
        self._destinations = [d for d in destinations if d.enabled]

        self._name_var = ctk.StringVar(value=rule.name if rule else "")
        self._pattern_var = ctk.StringVar(value=rule.pattern if rule else "")
        self._match_var = ctk.StringVar(value=rule.match_type if rule else "contains")
        self._case_var = ctk.BooleanVar(value=rule.case_sensitive if rule else False)
        self._prio_var = ctk.StringVar(value=str(rule.priority) if rule else "100")
        self._enabled_var = ctk.BooleanVar(value=rule.enabled if rule else True)

        dest_names = [d.name for d in self._destinations]
        selected_name = ""
        if rule:
            for d in self._destinations:
                if d.id == rule.destination_id:
                    selected_name = d.name
                    break
        self._dest_var = ctk.StringVar(value=selected_name or (dest_names[0] if dest_names else ""))

        rows = [
            ("Name:", ctk.CTkEntry(self, textvariable=self._name_var, width=300)),
            ("Pattern:", ctk.CTkEntry(self, textvariable=self._pattern_var, width=300)),
            ("Match type:", ctk.CTkComboBox(self, values=_MATCH_TYPES, variable=self._match_var, width=200)),
            ("Destination:", ctk.CTkComboBox(self, values=dest_names, variable=self._dest_var, width=200)),
            ("Priority:", ctk.CTkEntry(self, textvariable=self._prio_var, width=80)),
        ]

        for i, (label, widget) in enumerate(rows):
            ctk.CTkLabel(self, text=label).grid(row=i, column=0, padx=12, pady=6, sticky="e")
            widget.grid(row=i, column=1, padx=4, pady=6, sticky="w")

        ctk.CTkLabel(self, text="Case sensitive:").grid(row=len(rows), column=0, padx=12, pady=6, sticky="e")
        ctk.CTkCheckBox(self, text="", variable=self._case_var).grid(row=len(rows), column=1, padx=4, sticky="w")

        ctk.CTkLabel(self, text="Enabled:").grid(row=len(rows)+1, column=0, padx=12, pady=6, sticky="e")
        ctk.CTkCheckBox(self, text="", variable=self._enabled_var).grid(row=len(rows)+1, column=1, padx=4, sticky="w")

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.grid(row=len(rows)+2, column=0, columnspan=2, pady=10)
        ctk.CTkButton(btn_frame, text="Save", command=self._save).pack(side="left", padx=8)
        ctk.CTkButton(btn_frame, text="Cancel", command=self.destroy, fg_color="gray40").pack(side="left", padx=8)

    def _save(self) -> None:
        name = self._name_var.get().strip()
        pattern = self._pattern_var.get().strip()
        dest_name = self._dest_var.get().strip()

        if not name or not pattern:
            messagebox.showwarning("Validation", "Name and Pattern are required.", parent=self)
            return

        dest = next((d for d in self._destinations if d.name == dest_name), None)
        if dest is None:
            messagebox.showwarning("Validation", "Please select a valid Destination.", parent=self)
            return

        try:
            priority = int(self._prio_var.get())
        except ValueError:
            messagebox.showwarning("Validation", "Priority must be an integer.", parent=self)
            return

        match_type_val = self._match_var.get()
        if match_type_val not in ("contains", "startswith", "endswith", "regex"):
            messagebox.showwarning("Validation", f"Invalid match type: {match_type_val!r}", parent=self)
            return

        self.result = Rule.new(
            name=name,
            pattern=pattern,
            match_type=cast("MatchType", match_type_val),
            case_sensitive=self._case_var.get(),
            priority=priority,
            destination_id=dest.id,
        )
        self.result.enabled = self._enabled_var.get()
        self.destroy()


# ──────────────────────────────────────────────────────────────────────────────
# Main Application Window
# ──────────────────────────────────────────────────────────────────────────────

class DentalRouterApp(ctk.CTk):

    def __init__(self) -> None:
        super().__init__()
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("Dental Router")
        self.geometry("1300x820")
        self.minsize(1100, 700)

        self._settings: AppSettings = load_settings()
        self._watcher: Optional[Watcher] = None
        self._items: list[DetectedItem] = []
        self._item_rows: dict[str, list[ctk.CTkLabel]] = {}  # item.id → [stat, rule, dest] labels
        self._queue: queue.Queue[DetectedItem] = queue.Queue()
        # Maps for row-selection in the Destinations / Rules tabs
        self._dest_row_map: dict[int, Destination] = {}   # widget id → Destination
        self._rule_row_map: dict[int, Rule] = {}          # widget id → Rule

        self._build_ui()
        self._load_settings_to_ui()
        self._poll_queue()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ================================================================== #
    # UI BUILD
    # ================================================================== #

    def _build_ui(self) -> None:
        self._tab_view = ctk.CTkTabview(self)
        self._tab_view.pack(fill="both", expand=True, padx=10, pady=10)

        self._tab_view.add("⚙ Settings")
        self._tab_view.add("📁 Destinations")
        self._tab_view.add("📋 Rules")
        self._tab_view.add("🔍 Monitor")

        self._build_settings_tab()
        self._build_destinations_tab()
        self._build_rules_tab()
        self._build_monitor_tab()

    # ------------------------------------------------------------------ #
    # Tab 1 – Settings
    # ------------------------------------------------------------------ #

    def _build_settings_tab(self) -> None:
        tab = self._tab_view.tab("⚙ Settings")

        form = ctk.CTkFrame(tab)
        form.pack(fill="x", padx=20, pady=20)

        # Source dir
        self._src_var = ctk.StringVar()
        self._quar_var = ctk.StringVar()

        row = 0
        ctk.CTkLabel(form, text="Source directory:").grid(row=row, column=0, sticky="e", padx=12, pady=8)
        ctk.CTkEntry(form, textvariable=self._src_var, width=420).grid(row=row, column=1, padx=4, pady=8, sticky="w")
        ctk.CTkButton(form, text="Browse", width=80, command=lambda: _browse_dir(self._src_var)).grid(row=row, column=2, padx=4)

        row += 1
        ctk.CTkLabel(form, text="Quarantine / no-rule dir:").grid(row=row, column=0, sticky="e", padx=12, pady=8)
        ctk.CTkEntry(form, textvariable=self._quar_var, width=420).grid(row=row, column=1, padx=4, pady=8, sticky="w")
        ctk.CTkButton(form, text="Browse", width=80, command=lambda: _browse_dir(self._quar_var)).grid(row=row, column=2, padx=4)

        # Auto-mode
        row += 1
        self._auto_var = ctk.BooleanVar()
        ctk.CTkLabel(form, text="Auto-copy mode:").grid(row=row, column=0, sticky="e", padx=12, pady=8)
        ctk.CTkCheckBox(form, text="Automatically copy when one rule matches", variable=self._auto_var).grid(row=row, column=1, padx=4, sticky="w")

        # on_no_match
        row += 1
        self._no_match_var = ctk.StringVar(value="manual")
        ctk.CTkLabel(form, text="On no-match:").grid(row=row, column=0, sticky="e", padx=12, pady=8)
        ctk.CTkComboBox(form, values=["manual", "quarantine"], variable=self._no_match_var, width=200).grid(row=row, column=1, padx=4, sticky="w")

        # on_conflict
        row += 1
        self._conflict_var = ctk.StringVar(value="manual")
        ctk.CTkLabel(form, text="On conflict:").grid(row=row, column=0, sticky="e", padx=12, pady=8)
        ctk.CTkComboBox(form, values=["manual", "quarantine"], variable=self._conflict_var, width=200).grid(row=row, column=1, padx=4, sticky="w")

        # debounce
        row += 1
        self._debounce_var = ctk.StringVar(value="2.0")
        ctk.CTkLabel(form, text="Scan debounce (s):").grid(row=row, column=0, sticky="e", padx=12, pady=8)
        ctk.CTkEntry(form, textvariable=self._debounce_var, width=80).grid(row=row, column=1, padx=4, sticky="w")

        # Save button
        row += 1
        ctk.CTkButton(form, text="💾 Save Settings", command=self._save_settings).grid(
            row=row, column=0, columnspan=3, pady=16,
        )

    # ------------------------------------------------------------------ #
    # Tab 2 – Destinations
    # ------------------------------------------------------------------ #

    def _build_destinations_tab(self) -> None:
        tab = self._tab_view.tab("📁 Destinations")

        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(10, 0))

        ctk.CTkButton(toolbar, text="➕ Add Destination", command=self._add_destination).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="✏ Edit", command=self._edit_destination).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="🗑 Remove", command=self._remove_destination, fg_color="#C0392B").pack(side="left", padx=4)

        # Table header
        hdr = ctk.CTkFrame(tab)
        hdr.pack(fill="x", padx=10, pady=(6, 0))
        for col, width in [("Name", 180), ("Path", 400), ("Enabled", 80)]:
            ctk.CTkLabel(hdr, text=col, font=ctk.CTkFont(weight="bold"), width=width, anchor="w").pack(side="left", padx=4)

        # Scrollable list
        self._dest_frame = ctk.CTkScrollableFrame(tab)
        self._dest_frame.pack(fill="both", expand=True, padx=10, pady=6)

    # ------------------------------------------------------------------ #
    # Tab 3 – Rules
    # ------------------------------------------------------------------ #

    def _build_rules_tab(self) -> None:
        tab = self._tab_view.tab("📋 Rules")

        toolbar = ctk.CTkFrame(tab, fg_color="transparent")
        toolbar.pack(fill="x", padx=10, pady=(10, 0))

        ctk.CTkButton(toolbar, text="➕ Add Rule", command=self._add_rule).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="✏ Edit", command=self._edit_rule).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="🗑 Remove", command=self._remove_rule, fg_color="#C0392B").pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="⬆ Priority", command=lambda: self._shift_rule_priority(-1)).pack(side="left", padx=4)
        ctk.CTkButton(toolbar, text="⬇ Priority", command=lambda: self._shift_rule_priority(+1)).pack(side="left", padx=4)

        # Table header
        hdr = ctk.CTkFrame(tab)
        hdr.pack(fill="x", padx=10, pady=(6, 0))
        for col, width in [("Prio", 50), ("Name", 160), ("Pattern", 180), ("Type", 100), ("Case", 60), ("Destination", 150), ("En", 40)]:
            ctk.CTkLabel(hdr, text=col, font=ctk.CTkFont(weight="bold"), width=width, anchor="w").pack(side="left", padx=2)

        self._rules_frame = ctk.CTkScrollableFrame(tab)
        self._rules_frame.pack(fill="both", expand=True, padx=10, pady=6)

    # ------------------------------------------------------------------ #
    # Tab 4 – Monitor
    # ------------------------------------------------------------------ #

    def _build_monitor_tab(self) -> None:
        tab = self._tab_view.tab("🔍 Monitor")

        # Top control bar
        ctrl = ctk.CTkFrame(tab, fg_color="transparent")
        ctrl.pack(fill="x", padx=10, pady=(10, 0))

        self._start_btn = ctk.CTkButton(ctrl, text="▶ Start Monitoring", width=180,
                                        command=self._toggle_monitoring, fg_color="#27AE60")
        self._start_btn.pack(side="left", padx=4)

        self._status_label = ctk.CTkLabel(ctrl, text="● Stopped", text_color="#E74C3C")
        self._status_label.pack(side="left", padx=12)

        ctk.CTkButton(ctrl, text="🗑 Clear List", width=120,
                      command=self._clear_items, fg_color="gray40").pack(side="right", padx=4)

        # Table header
        hdr = ctk.CTkFrame(tab, fg_color="#1A1A2E")
        hdr.pack(fill="x", padx=10, pady=(6, 0))
        for col, width in [
            ("Name", 220), ("Type", 60), ("Rule", 160), ("Destination", 150),
            ("Status", 90), ("Time", 130), ("Actions", 270),
        ]:
            ctk.CTkLabel(hdr, text=col, font=ctk.CTkFont(weight="bold"), width=width, anchor="w",
                         text_color="white").pack(side="left", padx=4, pady=4)

        # Scrollable rows
        self._monitor_frame = ctk.CTkScrollableFrame(tab)
        self._monitor_frame.pack(fill="both", expand=True, padx=10, pady=4)

    # ================================================================== #
    # SETTINGS LOAD/SAVE
    # ================================================================== #

    def _load_settings_to_ui(self) -> None:
        s = self._settings
        self._src_var.set(s.source_dir)
        self._quar_var.set(s.quarantine_dir)
        self._auto_var.set(s.auto_mode)
        self._no_match_var.set(s.on_no_match)
        self._conflict_var.set(s.on_conflict)
        self._debounce_var.set(str(s.scan_debounce_seconds))
        self._refresh_destinations_list()
        self._refresh_rules_list()

    def _save_settings(self) -> None:
        try:
            debounce = float(self._debounce_var.get())
        except ValueError:
            messagebox.showwarning("Validation", "Debounce must be a number.")
            return

        no_match_val = self._no_match_var.get()
        conflict_val = self._conflict_var.get()
        if no_match_val not in ("manual", "quarantine"):
            messagebox.showwarning("Validation", f"Invalid on_no_match value: {no_match_val!r}")
            return
        if conflict_val not in ("manual", "quarantine"):
            messagebox.showwarning("Validation", f"Invalid on_conflict value: {conflict_val!r}")
            return

        self._settings.source_dir = self._src_var.get().strip()
        self._settings.quarantine_dir = self._quar_var.get().strip()
        self._settings.auto_mode = self._auto_var.get()
        self._settings.on_no_match = cast(Literal["manual", "quarantine"], no_match_val)
        self._settings.on_conflict = cast(Literal["manual", "quarantine"], conflict_val)
        self._settings.scan_debounce_seconds = debounce

        try:
            save_settings(self._settings)
            logger.info("Settings saved.")
            messagebox.showinfo("Saved", "Settings saved successfully.")
        except Exception as exc:
            logger.error(f"Failed to save settings: {exc}")
            messagebox.showerror("Error", f"Could not save settings:\n{exc}")

    # ================================================================== #
    # DESTINATIONS
    # ================================================================== #

    def _refresh_destinations_list(self) -> None:
        for widget in self._dest_frame.winfo_children():
            widget.destroy()
        self._dest_row_map.clear()

        for i, dest in enumerate(self._settings.destinations):
            row = ctk.CTkFrame(self._dest_frame, fg_color=("#2B2B3B" if i % 2 else "#222233"))
            row.pack(fill="x", pady=1)
            row.bind("<Button-1>", lambda e, d=dest: self._select_destination(d))
            self._dest_row_map[id(row)] = dest

            ctk.CTkLabel(row, text=dest.name, width=180, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text=dest.path, width=400, anchor="w").pack(side="left", padx=4)
            ctk.CTkLabel(row, text="✔" if dest.enabled else "✘", width=80, anchor="w",
                         text_color="#2ECC71" if dest.enabled else "#E74C3C").pack(side="left")

        self._selected_dest: Optional[Destination] = None

    def _select_destination(self, dest: Destination) -> None:
        self._selected_dest = dest

    def _add_destination(self) -> None:
        dlg = DestinationDialog(self)
        self.wait_window(dlg)
        if dlg.result:
            self._settings.destinations.append(dlg.result)
            save_settings(self._settings)
            self._refresh_destinations_list()
            self._refresh_rules_list()

    def _edit_destination(self) -> None:
        dest = self._selected_dest
        if dest is None:
            messagebox.showinfo("Select", "Please click a destination row first.")
            return
        dlg = DestinationDialog(self, dest=dest)
        self.wait_window(dlg)
        if dlg.result:
            dlg.result.id = dest.id  # keep original ID
            idx = next(i for i, d in enumerate(self._settings.destinations) if d.id == dest.id)
            self._settings.destinations[idx] = dlg.result
            save_settings(self._settings)
            self._refresh_destinations_list()
            self._refresh_rules_list()

    def _remove_destination(self) -> None:
        dest = self._selected_dest
        if dest is None:
            messagebox.showinfo("Select", "Please click a destination row first.")
            return
        if not messagebox.askyesno("Confirm", f"Remove destination '{dest.name}'?"):
            return
        self._settings.destinations = [d for d in self._settings.destinations if d.id != dest.id]
        # also remove dependent rules
        self._settings.rules = [r for r in self._settings.rules if r.destination_id != dest.id]
        save_settings(self._settings)
        self._refresh_destinations_list()
        self._refresh_rules_list()

    # ================================================================== #
    # RULES
    # ================================================================== #

    def _refresh_rules_list(self) -> None:
        for widget in self._rules_frame.winfo_children():
            widget.destroy()
        self._rule_row_map.clear()

        dest_map = {d.id: d.name for d in self._settings.destinations}
        sorted_rules = sorted(self._settings.rules, key=lambda r: (r.priority, r.name))

        for i, rule in enumerate(sorted_rules):
            row = ctk.CTkFrame(self._rules_frame, fg_color=("#2B2B3B" if i % 2 else "#222233"))
            row.pack(fill="x", pady=1)
            row.bind("<Button-1>", lambda e, r=rule: self._select_rule(r))
            self._rule_row_map[id(row)] = rule

            ctk.CTkLabel(row, text=str(rule.priority), width=50, anchor="w").pack(side="left", padx=2)
            ctk.CTkLabel(row, text=rule.name, width=160, anchor="w").pack(side="left", padx=2)
            ctk.CTkLabel(row, text=rule.pattern, width=180, anchor="w").pack(side="left", padx=2)
            ctk.CTkLabel(row, text=rule.match_type, width=100, anchor="w").pack(side="left", padx=2)
            ctk.CTkLabel(row, text="✔" if rule.case_sensitive else "✘", width=60, anchor="w").pack(side="left", padx=2)
            ctk.CTkLabel(row, text=dest_map.get(rule.destination_id, "?"), width=150, anchor="w").pack(side="left", padx=2)
            ctk.CTkLabel(row, text="✔" if rule.enabled else "✘", width=40, anchor="w",
                         text_color="#2ECC71" if rule.enabled else "#E74C3C").pack(side="left")

        self._selected_rule: Optional[Rule] = None

    def _select_rule(self, rule: Rule) -> None:
        self._selected_rule = rule

    def _add_rule(self) -> None:
        if not self._settings.destinations:
            messagebox.showwarning("No Destinations", "Add at least one destination first.")
            return
        dlg = RuleDialog(self, self._settings.destinations)
        self.wait_window(dlg)
        if dlg.result:
            self._settings.rules.append(dlg.result)
            save_settings(self._settings)
            self._refresh_rules_list()

    def _edit_rule(self) -> None:
        rule = self._selected_rule
        if rule is None:
            messagebox.showinfo("Select", "Please click a rule row first.")
            return
        dlg = RuleDialog(self, self._settings.destinations, rule=rule)
        self.wait_window(dlg)
        if dlg.result:
            dlg.result.id = rule.id  # keep original ID
            idx = next(i for i, r in enumerate(self._settings.rules) if r.id == rule.id)
            self._settings.rules[idx] = dlg.result
            save_settings(self._settings)
            self._refresh_rules_list()

    def _remove_rule(self) -> None:
        rule = self._selected_rule
        if rule is None:
            messagebox.showinfo("Select", "Please click a rule row first.")
            return
        if not messagebox.askyesno("Confirm", f"Remove rule '{rule.name}'?"):
            return
        self._settings.rules = [r for r in self._settings.rules if r.id != rule.id]
        save_settings(self._settings)
        self._refresh_rules_list()

    def _shift_rule_priority(self, delta: int) -> None:
        rule = self._selected_rule
        if rule is None:
            messagebox.showinfo("Select", "Please click a rule row first.")
            return
        for r in self._settings.rules:
            if r.id == rule.id:
                r.priority = max(1, r.priority + delta)
                break
        save_settings(self._settings)
        self._refresh_rules_list()

    # ================================================================== #
    # MONITORING
    # ================================================================== #

    def _toggle_monitoring(self) -> None:
        if self._watcher and self._watcher.is_running:
            self._stop_monitoring()
        else:
            self._start_monitoring()

    def _start_monitoring(self) -> None:
        src = self._src_var.get().strip()
        if not src:
            messagebox.showwarning("Missing", "Please set a Source Directory in Settings.")
            return
        if not Path(src).is_dir():
            messagebox.showwarning("Not found", f"Source directory does not exist:\n{src}")
            return

        # Re-read settings from disk in case user edited them
        self._settings = load_settings()
        self._load_settings_to_ui()

        debounce = self._settings.scan_debounce_seconds
        self._watcher = Watcher(src, self._on_item_detected, debounce)

        try:
            self._watcher.start()
        except Exception as exc:
            logger.error(f"Failed to start watcher: {exc}")
            messagebox.showerror("Error", f"Cannot start watcher:\n{exc}")
            return

        self._start_btn.configure(text="⏹ Stop Monitoring", fg_color="#C0392B")
        self._status_label.configure(text="● Monitoring", text_color="#2ECC71")
        logger.info(f"Monitoring started: {src}")

    def _stop_monitoring(self) -> None:
        if self._watcher:
            self._watcher.stop()
            self._watcher = None
        self._start_btn.configure(text="▶ Start Monitoring", fg_color="#27AE60")
        self._status_label.configure(text="● Stopped", text_color="#E74C3C")

    def _on_item_detected(self, item: DetectedItem) -> None:
        """Called by the Watcher thread – just enqueue."""
        self._queue.put(item)

    def _poll_queue(self) -> None:
        """Drain the queue on the GUI thread every 200 ms."""
        try:
            while True:
                item = self._queue.get_nowait()
                self._process_item(item)
        except queue.Empty:
            pass
        finally:
            self.after(200, self._poll_queue)

    def _process_item(self, item: DetectedItem) -> None:
        """Route item and potentially auto-copy; then show in Monitor tab."""
        self._settings = load_settings()

        status_str, dest_id, rule_name = route_item(item, self._settings)

        if status_str == "ok":
            dest = get_destination(dest_id, self._settings)  # type: ignore[arg-type]
            item.rule_applied = rule_name
            if dest:
                item.destination_id = dest.id
                item.destination_name = dest.name
                if self._settings.auto_mode:
                    self._do_copy(item, dest.path)
                    return  # row added inside _do_copy
                else:
                    item.status = "pending"
            else:
                item.status = "error"
                item.error_msg = f"Destination {dest_id} not found or disabled."

        elif status_str == "conflict":
            item.status = "conflict"
            item.rule_applied = "<conflict>"
            if self._settings.on_conflict == "quarantine":
                self._copy_to_quarantine(item)
                return

        elif status_str == "no_match":
            item.status = "no_match"
            item.rule_applied = "<no match>"
            if self._settings.on_no_match == "quarantine":
                self._copy_to_quarantine(item)
                return

        self._items.append(item)
        self._add_monitor_row(item)

    def _do_copy(self, item: DetectedItem, dest_path: str) -> None:
        """Perform the actual copy in a background thread."""
        item.status = "pending"
        self._items.append(item)
        self._add_monitor_row(item)

        def _worker() -> None:
            result = copy_item(Path(item.path), Path(dest_path))
            if result:
                item.status = "copied"
            else:
                item.status = "error"
                item.error_msg = "Copy failed – see logs."
            self.after(0, lambda: self._update_row(item))

        threading.Thread(target=_worker, daemon=True).start()

    def _copy_to_quarantine(self, item: DetectedItem) -> None:
        qdir = self._settings.quarantine_dir
        if not qdir:
            logger.warning("Quarantine directory not configured.")
            item.status = "error"
            item.error_msg = "Quarantine dir not set."
            self._items.append(item)
            self._add_monitor_row(item)
            return

        item.destination_name = "Quarantine"
        item.status = "pending"
        self._items.append(item)
        self._add_monitor_row(item)

        def _worker() -> None:
            result = copy_item(Path(item.path), Path(qdir))
            item.status = "copied" if result else "error"
            if not result:
                item.error_msg = "Quarantine copy failed."
            self.after(0, lambda: self._update_row(item))

        threading.Thread(target=_worker, daemon=True).start()

    # ================================================================== #
    # MONITOR TABLE ROWS
    # ================================================================== #

    def _add_monitor_row(self, item: DetectedItem) -> None:
        row_frame = ctk.CTkFrame(self._monitor_frame, fg_color="#1E1E2E")
        row_frame.pack(fill="x", pady=1)

        color = _STATUS_COLORS.get(item.status, "white")

        lbl_name = ctk.CTkLabel(row_frame, text=item.name, width=220, anchor="w")
        lbl_type = ctk.CTkLabel(row_frame, text=item.item_type, width=60, anchor="w")
        lbl_rule = ctk.CTkLabel(row_frame, text=item.rule_applied or "—", width=160, anchor="w")
        lbl_dest = ctk.CTkLabel(row_frame, text=item.destination_name or "—", width=150, anchor="w")
        lbl_stat = ctk.CTkLabel(row_frame, text=item.status, width=90, anchor="w", text_color=color)
        lbl_time = ctk.CTkLabel(row_frame, text=item.timestamp.strftime("%H:%M:%S"), width=130, anchor="w")

        lbl_name.pack(side="left", padx=4, pady=3)
        lbl_type.pack(side="left", padx=4)
        lbl_rule.pack(side="left", padx=4)
        lbl_dest.pack(side="left", padx=4)
        lbl_stat.pack(side="left", padx=4)
        lbl_time.pack(side="left", padx=4)

        # Action buttons
        actions = ctk.CTkFrame(row_frame, fg_color="transparent")
        actions.pack(side="left", padx=4)

        ctk.CTkButton(
            actions, text="Copy to…", width=80,
            command=lambda i=item, s=lbl_stat: self._manual_copy(i, s),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            actions, text="Auto-rule", width=80,
            command=lambda i=item, s=lbl_stat: self._auto_rule(i, s),
        ).pack(side="left", padx=2)

        ctk.CTkButton(
            actions, text="Ignore", width=70, fg_color="gray40",
            command=lambda i=item, s=lbl_stat: self._ignore_item(i, s),
        ).pack(side="left", padx=2)

        # Store label refs for updates
        self._item_rows[item.id] = [lbl_stat, lbl_rule, lbl_dest]

    def _update_row(self, item: DetectedItem) -> None:
        refs = self._item_rows.get(item.id)
        if not refs:
            return
        lbl_stat, lbl_rule, lbl_dest = refs
        color = _STATUS_COLORS.get(item.status, "white")
        lbl_stat.configure(text=item.status, text_color=color)
        lbl_rule.configure(text=item.rule_applied or "—")
        lbl_dest.configure(text=item.destination_name or "—")

    def _manual_copy(self, item: DetectedItem, lbl_stat: ctk.CTkLabel) -> None:
        """Let user pick a destination and copy."""
        enabled = [d for d in self._settings.destinations if d.enabled]
        if not enabled:
            messagebox.showwarning("No Destinations", "No enabled destinations configured.")
            return

        # Simple selection dialog using tk
        names = [d.name for d in enabled]
        win = ctk.CTkToplevel(self)
        win.title("Select Destination")
        win.geometry("320x200")
        win.grab_set()

        ctk.CTkLabel(win, text=f"Copy '{item.name}' to:").pack(pady=10)
        var = ctk.StringVar(value=names[0])
        for name in names:
            ctk.CTkRadioButton(win, text=name, variable=var, value=name).pack(anchor="w", padx=20)

        def _ok() -> None:
            chosen = next((d for d in enabled if d.name == var.get()), None)
            win.destroy()
            if chosen:
                item.destination_name = chosen.name
                item.destination_id = chosen.id
                self._do_copy_manual(item)

        ctk.CTkButton(win, text="Copy", command=_ok).pack(pady=10)

    def _do_copy_manual(self, item: DetectedItem) -> None:
        dest = get_destination(item.destination_id or "", self._settings)
        if not dest:
            messagebox.showerror("Error", "Destination not found or disabled.")
            return
        self._update_row(item)

        def _worker() -> None:
            result = copy_item(Path(item.path), Path(dest.path))
            if result:
                item.status = "copied"
            else:
                item.status = "error"
                item.error_msg = "Copy failed – see logs."
            self.after(0, lambda: self._update_row(item))

        threading.Thread(target=_worker, daemon=True).start()

    def _auto_rule(self, item: DetectedItem, lbl_stat: ctk.CTkLabel) -> None:
        """Re-evaluate rules and copy if one rule matches."""
        status_str, dest_id, rule_name = route_item(item, self._settings)
        if status_str == "ok" and dest_id:
            dest = get_destination(dest_id, self._settings)
            if dest:
                item.rule_applied = rule_name
                item.destination_id = dest.id
                item.destination_name = dest.name
                self._do_copy(item, dest.path)
            else:
                messagebox.showerror("Error", "Destination not found or disabled.")
        elif status_str == "conflict":
            messagebox.showwarning("Conflict", "Multiple rules match with the same priority.\nUse 'Copy to…' to select manually.")
        else:
            messagebox.showinfo("No Match", "No rule matched this item.")

    def _ignore_item(self, item: DetectedItem, lbl_stat: ctk.CTkLabel) -> None:
        item.status = "ignored"
        self._update_row(item)

    def _clear_items(self) -> None:
        self._items.clear()
        self._item_rows.clear()
        for w in self._monitor_frame.winfo_children():
            w.destroy()

    # ================================================================== #
    # CLEANUP
    # ================================================================== #

    def _on_close(self) -> None:
        self._stop_monitoring()
        self.destroy()
