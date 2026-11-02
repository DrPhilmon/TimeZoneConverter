#!/usr/bin/env python3
"""
Time Zone Converter — a Tkinter GUI around convert_timezone().

Run:  python3 timezone_gui.py
Needs: Python 3.9+ with Tkinter, and timezone_converter.py in the same folder.
Windows: also run `pip install tzdata` (Windows has no built-in IANA time zone database).
"""

import os
import tkinter as tk
from dataclasses import dataclass, field
from datetime import datetime
from tkinter import ttk
from typing import Optional
from zoneinfo import ZoneInfo, available_timezones

from timezone_converter import convert_timezone


# ═════════════════════════════════════════════════════════════════════════════
# Logic (no GUI code here, so it can be tested without a screen)
# ═════════════════════════════════════════════════════════════════════════════
def load_zones() -> list[str]:
    """All IANA zone names, sorted. Empty if no tz database is installed."""
    return sorted(z for z in available_timezones() if "/" in z or z == "UTC")


def detect_local_zone(zones: list[str]) -> str:
    """Best-effort guess of this computer's IANA zone; falls back to UTC."""
    candidates = [os.environ.get("TZ", "")]
    try:
        real = os.path.realpath("/etc/localtime")          # Linux / macOS
        if "zoneinfo/" in real:
            candidates.append(real.split("zoneinfo/", 1)[1])
    except OSError:
        pass
    try:
        with open("/etc/timezone") as f:                    # Debian / Ubuntu
            candidates.append(f.read().strip())
    except OSError:
        pass
    for c in candidates:
        if c in zones:
            return c
    return "UTC"


def parse_datetime(date_text: str, time_text: str) -> datetime:
    """Parse 'YYYY-MM-DD' and 'HH:MM' or 'HH:MM:SS' (24-hour) into a datetime with no zone."""
    try:
        d = datetime.strptime(date_text.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Date must be a real date in the form YYYY-MM-DD, e.g. 2026-11-02.")
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            t = datetime.strptime(time_text.strip(), fmt).time()
            break
        except ValueError:
            continue
    else:
        raise ValueError("Time must be 24-hour HH:MM or HH:MM:SS, e.g. 14:57.")
    return datetime.combine(d, t)


def dst_status(naive: datetime, zone: str) -> Optional[str]:
    """
    'gap'     -> this wall-clock time never happened (clocks jumped forward)
    'overlap' -> this wall-clock time happened twice (clocks went back)
    None      -> normal time
    """
    z = ZoneInfo(zone)
    first, second = naive.replace(tzinfo=z, fold=0), naive.replace(tzinfo=z, fold=1)
    if first.utcoffset() == second.utcoffset():
        return None
    round_trip = first.astimezone(ZoneInfo("UTC")).astimezone(z).replace(tzinfo=None)
    return "overlap" if round_trip == naive else "gap"


def format_offset(dt: datetime) -> str:
    minutes = int(dt.utcoffset().total_seconds() // 60)
    sign = "+" if minutes >= 0 else "−"
    h, m = divmod(abs(minutes), 60)
    return f"UTC{sign}{h:02d}:{m:02d}"


@dataclass
class Conversion:
    source: datetime                     # aware, in from_tz
    result: datetime                     # aware, in to_tz
    notes: list[str] = field(default_factory=list)


def run_conversion(date_text: str, time_text: str, from_tz: str, to_tz: str,
                   zones: list[str]) -> Conversion:
    """Validate the GUI inputs, call convert_timezone(), and collect user-facing notes."""
    zone_set = set(zones)
    for label, z in (("From", from_tz), ("To", to_tz)):
        if not z.strip():
            raise ValueError(f"Please choose a '{label}' time zone.")
        if z not in zone_set:
            raise ValueError(f"'{z}' is not a known time zone. Pick one from the {label} list.")

    naive = parse_datetime(date_text, time_text)
    result = convert_timezone(naive, from_tz, to_tz)       # ← the wrapped function
    source = naive.replace(tzinfo=ZoneInfo(from_tz))
    notes = []

    status = dst_status(naive, from_tz)
    if status == "gap":
        notes.append(f"⚠ {naive:%H:%M} never happened on {naive:%d %b %Y} in {from_tz} "
                     f"(the clocks jumped forward). It was read using the offset from before the change.")
    elif status == "overlap":
        second = convert_timezone(naive.replace(fold=1), from_tz, to_tz)
        notes.append(f"⚠ {naive:%H:%M} happened twice on {naive:%d %b %Y} in {from_tz} "
                     f"(the clocks went back). Showing the first occurrence; the second one "
                     f"is {second:%Y-%m-%d %H:%M} {second.tzname()}.")

    day_shift = (result.date() - naive.date()).days
    if day_shift:
        word = {1: "the next day", -1: "the previous day"}.get(day_shift, f"{day_shift:+d} days")
        notes.append(f"↪ The converted time falls on {word}.")
    return Conversion(source, result, notes)


# ═════════════════════════════════════════════════════════════════════════════
# GUI
# ═════════════════════════════════════════════════════════════════════════════
class FilterCombobox(ttk.Combobox):
    """Combobox whose dropdown list narrows as you type (e.g. 'new y' -> America/New_York)."""

    def __init__(self, master, all_values: list[str], **kw):
        super().__init__(master, values=all_values, **kw)
        self._all = all_values
        self.bind("<KeyRelease>", self._filter)

    def _filter(self, event):
        if event.keysym in ("Up", "Down", "Return", "Escape", "Tab"):
            return
        text = self.get().strip().lower().replace(" ", "_")
        self["values"] = [z for z in self._all if text in z.lower()] if text else self._all


class TimezoneConverterApp(ttk.Frame):
    ACCENT = "#2563eb"
    ERROR = "#dc2626"
    WARN = "#b45309"
    MUTED = "#6b7280"

    def __init__(self, master: tk.Tk):
        super().__init__(master, padding=20)
        self.master = master
        self.zones = load_zones()
        self._build_styles()
        self._build_widgets()
        self.grid(sticky="nsew")
        master.columnconfigure(0, weight=1)
        master.rowconfigure(0, weight=1)
        master.bind("<Return>", lambda e: self.convert())

        if not self.zones:
            self.convert_btn.state(["disabled"])
            self._show_error("No time zone database found. Install it with:  pip install tzdata")
        else:
            self.fill_now()

    # ── layout ──────────────────────────────────────────────────────────────
    def _build_styles(self):
        s = ttk.Style(self.master)
        if "clam" in s.theme_names():
            s.theme_use("clam")
        s.configure("Title.TLabel", font=("TkDefaultFont", 16, "bold"))
        s.configure("Field.TLabel", font=("TkDefaultFont", 10, "bold"))
        s.configure("Hint.TLabel", foreground=self.MUTED)
        s.configure("Result.TLabel", font=("TkDefaultFont", 18, "bold"), foreground=self.ACCENT)
        s.configure("Detail.TLabel", foreground=self.MUTED)
        s.configure("Error.TLabel", foreground=self.ERROR)
        s.configure("Note.TLabel", foreground=self.WARN)
        s.configure("Convert.TButton", font=("TkDefaultFont", 11, "bold"), padding=(20, 8),
                    foreground="white", background=self.ACCENT)
        s.map("Convert.TButton", background=[("active", "#1d4ed8"), ("disabled", "#93c5fd")])

    def _build_widgets(self):
        self.columnconfigure(1, weight=1)
        self.columnconfigure(0, minsize=140)
        ttk.Label(self, text="🌍 Time Zone Converter", style="Title.TLabel").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 14))

        # Date & time
        ttk.Label(self, text="Date and time", style="Field.TLabel").grid(row=1, column=0, sticky="w")
        dt_row = ttk.Frame(self)
        dt_row.grid(row=1, column=1, columnspan=2, sticky="w", pady=4)
        self.date_var, self.time_var = tk.StringVar(), tk.StringVar()
        self.date_entry = ttk.Entry(dt_row, textvariable=self.date_var, width=12)
        self.time_entry = ttk.Entry(dt_row, textvariable=self.time_var, width=9)
        self.date_entry.pack(side="left")
        self.time_entry.pack(side="left", padx=(6, 6))
        ttk.Button(dt_row, text="Now", command=self.fill_now, width=5).pack(side="left")
        ttk.Label(self, text="YYYY-MM-DD   HH:MM (24-hour)", style="Hint.TLabel").grid(
            row=2, column=1, columnspan=2, sticky="w")

        # Zones
        local = detect_local_zone(self.zones) if self.zones else ""
        self.from_var = tk.StringVar(value=local)
        self.to_var = tk.StringVar(value="UTC" if local != "UTC" else "America/New_York")

        ttk.Label(self, text="From time zone", style="Field.TLabel").grid(
            row=3, column=0, sticky="w", pady=(12, 4))
        self.from_combo = FilterCombobox(self, self.zones, textvariable=self.from_var, width=32)
        self.from_combo.grid(row=3, column=1, sticky="ew", pady=(12, 4))

        ttk.Button(self, text="⇅ Swap", command=self.swap).grid(
            row=3, column=2, rowspan=2, padx=(8, 0), sticky="ns", pady=(12, 4))

        ttk.Label(self, text="To time zone", style="Field.TLabel").grid(row=4, column=0, sticky="w", pady=4)
        self.to_combo = FilterCombobox(self, self.zones, textvariable=self.to_var, width=32)
        self.to_combo.grid(row=4, column=1, sticky="ew", pady=4)
        ttk.Label(self, text="Tip: type part of a name (e.g. “tokyo”) to filter the list",
                  style="Hint.TLabel").grid(row=5, column=1, columnspan=2, sticky="w")

        # Convert
        self.convert_btn = ttk.Button(self, text="Convert", style="Convert.TButton", command=self.convert)
        self.convert_btn.grid(row=6, column=0, columnspan=3, pady=16)

        # Output
        ttk.Separator(self).grid(row=7, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        ttk.Label(self, text="Converted date and time", style="Field.TLabel").grid(
            row=8, column=0, columnspan=3, sticky="w")
        self.result_var = tk.StringVar(value="—")
        self.detail_var = tk.StringVar()
        self.notes_var = tk.StringVar()
        self.error_var = tk.StringVar()
        ttk.Label(self, textvariable=self.result_var, style="Result.TLabel").grid(
            row=9, column=0, columnspan=3, sticky="w", pady=(4, 0))
        ttk.Label(self, textvariable=self.detail_var, style="Detail.TLabel", wraplength=460,
                  justify="left").grid(row=10, column=0, columnspan=3, sticky="w")
        ttk.Label(self, textvariable=self.notes_var, style="Note.TLabel", wraplength=460,
                  justify="left").grid(row=11, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Label(self, textvariable=self.error_var, style="Error.TLabel", wraplength=460,
                  justify="left").grid(row=12, column=0, columnspan=3, sticky="w", pady=(6, 0))

    # ── actions ─────────────────────────────────────────────────────────────
    def fill_now(self):
        """Fill date/time with the current time in the selected 'From' zone."""
        zone = self.from_var.get() if self.from_var.get() in self.zones else "UTC"
        now = datetime.now(ZoneInfo(zone))
        self.date_var.set(now.strftime("%Y-%m-%d"))
        self.time_var.set(now.strftime("%H:%M"))

    def swap(self):
        f, t = self.from_var.get(), self.to_var.get()
        self.from_var.set(t)
        self.to_var.set(f)

    def convert(self):
        self.error_var.set("")
        try:
            c = run_conversion(self.date_var.get(), self.time_var.get(),
                               self.from_var.get(), self.to_var.get(), self.zones)
        except Exception as e:                      # show every problem in the window
            self._show_error(f"✘ {e}")
            return
        r, s = c.result, c.source
        self.result_var.set(f"{r:%A %d %B %Y, %H:%M}" + (f":{r:%S}" if r.second else ""))
        self.detail_var.set(
            f"{self.to_var.get()} · {r.tzname()} · {format_offset(r)}\n"
            f"from {s:%Y-%m-%d %H:%M} {s.tzname()} ({format_offset(s)}) in {self.from_var.get()}")
        self.notes_var.set("\n".join(c.notes))

    def _show_error(self, message: str):
        self.result_var.set("—")
        self.detail_var.set("")
        self.notes_var.set("")
        self.error_var.set(message)


def main():
    root = tk.Tk()
    root.title("Time Zone Converter")
    root.minsize(520, 0)
    TimezoneConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
