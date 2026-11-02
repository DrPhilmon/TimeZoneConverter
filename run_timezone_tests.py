#!/usr/bin/env python3
"""
Standalone test program for convert_timezone().

Needs only the Python standard library (3.9+). Put it next to timezone_converter.py and run:

    python3 run_timezone_tests.py            # coloured report
    python3 run_timezone_tests.py -v         # also list every passing case
    python3 run_timezone_tests.py --no-color # plain text (for logs / CI)

Exit code: 0 if every case passes (skips allowed), 1 otherwise.
"""

import argparse
import sys
import time as _time
import traceback
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from timezone_converter import convert_timezone


# ═════════════════════════════════════════════════════════════════════════════
# Mini test framework
# ═════════════════════════════════════════════════════════════════════════════
class SkipCase(Exception):
    """Raise inside a case to mark it skipped (e.g. feature missing on this machine)."""


@dataclass
class Case:
    category: str
    name: str
    run: Callable[[], None]


@dataclass
class Result:
    case: Case
    status: str          # PASS | FAIL | ERROR | SKIP
    detail: str = ""


CASES: list[Case] = []


def add(category: str, name: str, fn: Callable[[], None]) -> None:
    CASES.append(Case(category, name, fn))


def wall(dt: datetime) -> tuple:
    """Local wall-clock reading (Y, M, D, h, m) — what a person would see on a clock."""
    return (dt.year, dt.month, dt.day, dt.hour, dt.minute)


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# ── Reusable case builders ───────────────────────────────────────────────────
def expect_wall(category, name, src, from_tz, to_tz, expected):
    def run():
        got = wall(convert_timezone(src, from_tz, to_tz))
        check(got == expected, f"expected {expected}, got {got}")
    add(category, name, run)


def expect_hm(category, name, src, from_tz, to_tz, expected_hm):
    def run():
        r = convert_timezone(src, from_tz, to_tz)
        got = (r.hour, r.minute)
        check(got == expected_hm, f"expected {expected_hm[0]:02d}:{expected_hm[1]:02d}, "
                                  f"got {got[0]:02d}:{got[1]:02d}")
    add(category, name, run)


def expect_raises(category, name, args, *exc_types):
    def run():
        try:
            convert_timezone(*args)
        except exc_types:
            return
        except Exception as e:  # wrong exception type
            raise AssertionError(
                f"expected {' or '.join(t.__name__ for t in exc_types)}, "
                f"got {type(e).__name__}: {e}")
        raise AssertionError(
            f"expected {' or '.join(t.__name__ for t in exc_types)}, but no error was raised")
    add(category, name, run)


# ═════════════════════════════════════════════════════════════════════════════
# 1. DIFFERENT DATES
# ═════════════════════════════════════════════════════════════════════════════
C = "1. Different dates"
expect_wall(C, "Midnight forward: Amsterdam 23:30 -> Tokyo next day",
            datetime(2026, 11, 2, 23, 30), "Europe/Amsterdam", "Asia/Tokyo", (2026, 11, 3, 7, 30))
expect_wall(C, "Midnight backward: Amsterdam 00:30 -> New York previous day",
            datetime(2026, 11, 2, 0, 30), "Europe/Amsterdam", "America/New_York", (2026, 11, 1, 18, 30))
expect_wall(C, "Month boundary: UTC 30 Apr 22:00 -> Kolkata 1 May",
            datetime(2026, 4, 30, 22, 0), "UTC", "Asia/Kolkata", (2026, 5, 1, 3, 30))
expect_wall(C, "Year boundary: UTC 31 Dec 23:00 -> Tokyo 2027",
            datetime(2026, 12, 31, 23, 0), "UTC", "Asia/Tokyo", (2027, 1, 1, 8, 0))
expect_wall(C, "Leap day forward: 29 Feb 2028 -> 1 Mar in Tokyo",
            datetime(2028, 2, 29, 20, 0), "UTC", "Asia/Tokyo", (2028, 3, 1, 5, 0))
expect_wall(C, "Leap day backward: 1 Mar 2028 -> 29 Feb in Los Angeles",
            datetime(2028, 3, 1, 2, 0), "UTC", "America/Los_Angeles", (2028, 2, 29, 18, 0))
expect_hm(C, "Historic rule: Moscow was UTC+4 in 2013",
          datetime(2013, 1, 15, 12, 0), "UTC", "Europe/Moscow", (16, 0))
expect_hm(C, "Historic rule: Moscow is UTC+3 since 2014",
          datetime(2020, 1, 15, 12, 0), "UTC", "Europe/Moscow", (15, 0))


# ═════════════════════════════════════════════════════════════════════════════
# 2. DAYLIGHT SAVING TIME
# ═════════════════════════════════════════════════════════════════════════════
C = "2. Daylight saving time"
expect_hm(C, "Summer: Amsterdam 12:00 CEST -> 10:00 UTC",
          datetime(2026, 7, 1, 12, 0), "Europe/Amsterdam", "UTC", (10, 0))
expect_hm(C, "Winter: Amsterdam 12:00 CET -> 11:00 UTC",
          datetime(2026, 12, 1, 12, 0), "Europe/Amsterdam", "UTC", (11, 0))
expect_hm(C, "Spring-forward: 00:59 UTC -> 01:59 Amsterdam (last minute of CET)",
          datetime(2026, 3, 29, 0, 59), "UTC", "Europe/Amsterdam", (1, 59))
expect_hm(C, "Spring-forward: 01:00 UTC -> 03:00 Amsterdam (02:xx skipped)",
          datetime(2026, 3, 29, 1, 0), "UTC", "Europe/Amsterdam", (3, 0))
expect_hm(C, "Non-existent 02:30 on 29 Mar is read as CET (documents current behaviour)",
          datetime(2026, 3, 29, 2, 30), "Europe/Amsterdam", "UTC", (1, 30))
expect_hm(C, "Ambiguous 02:30 on 25 Oct, fold=0 -> first occurrence (CEST)",
          datetime(2026, 10, 25, 2, 30, fold=0), "Europe/Amsterdam", "UTC", (0, 30))
expect_hm(C, "Ambiguous 02:30 on 25 Oct, fold=1 -> second occurrence (CET)",
          datetime(2026, 10, 25, 2, 30, fold=1), "Europe/Amsterdam", "UTC", (1, 30))
expect_hm(C, "US/EU mismatch: both standard (1 Mar) -> 6 h gap",
          datetime(2026, 3, 1, 12, 0), "America/New_York", "Europe/Amsterdam", (18, 0))
expect_hm(C, "US/EU mismatch: only US on DST (15 Mar) -> 5 h gap",
          datetime(2026, 3, 15, 12, 0), "America/New_York", "Europe/Amsterdam", (17, 0))
expect_hm(C, "US/EU mismatch: both DST (15 Apr) -> 6 h gap",
          datetime(2026, 4, 15, 12, 0), "America/New_York", "Europe/Amsterdam", (18, 0))
expect_hm(C, "US/EU mismatch: only US on DST (28 Oct) -> 5 h gap",
          datetime(2026, 10, 28, 12, 0), "America/New_York", "Europe/Amsterdam", (17, 0))
expect_hm(C, "Southern hemisphere: January, Amsterdam -> Sydney is +10 h",
          datetime(2026, 1, 15, 12, 0), "Europe/Amsterdam", "Australia/Sydney", (22, 0))
expect_hm(C, "Southern hemisphere: July, Amsterdam -> Sydney is +8 h",
          datetime(2026, 7, 15, 12, 0), "Europe/Amsterdam", "Australia/Sydney", (20, 0))


def _tokyo_stable():
    for m in range(1, 13):
        off = convert_timezone(datetime(2026, m, 1), "UTC", "Asia/Tokyo").utcoffset()
        check(off == timedelta(hours=9), f"month {m}: offset {off}, expected +9:00")
add(C, "No-DST zone: Tokyo is UTC+9 in all 12 months", _tokyo_stable)


# ═════════════════════════════════════════════════════════════════════════════
# 3. BETWEEN DIFFERENT TIME ZONES
# ═════════════════════════════════════════════════════════════════════════════
C = "3. Between different zones"
MEETING = datetime(2026, 11, 2, 14, 57)
for zone, exp, label in [
    ("America/New_York",   (2026, 11, 2, 8, 57),  "negative offset"),
    ("Asia/Tokyo",         (2026, 11, 2, 22, 57), "positive offset"),
    ("Africa/Addis_Ababa", (2026, 11, 2, 16, 57), "no DST"),
    ("Asia/Kolkata",       (2026, 11, 2, 19, 27), "+5:30 half-hour"),
    ("Asia/Kathmandu",     (2026, 11, 2, 19, 42), "+5:45 quarter-hour"),
    ("UTC",                (2026, 11, 2, 13, 57), "UTC"),
]:
    expect_wall(C, f"Amsterdam 14:57 -> {zone} ({label})", MEETING, "Europe/Amsterdam", zone, exp)


def _date_line():
    src = datetime(2026, 6, 1, 12, 0)
    kiri = convert_timezone(src, "UTC", "Pacific/Kiritimati")
    pago = convert_timezone(src, "UTC", "Pacific/Pago_Pago")
    check(wall(kiri) == (2026, 6, 2, 2, 0), f"Kiritimati got {wall(kiri)}")
    check(wall(pago) == (2026, 6, 1, 1, 0), f"Pago Pago got {wall(pago)}")
    check(kiri == pago, "the two results should be the same instant")
add(C, "Date line: Kiritimati (+14) vs Pago Pago (-11), same instant", _date_line)


def _precision():
    r = convert_timezone(datetime(2026, 11, 2, 14, 57, 33, 123456), "Europe/Amsterdam", "Asia/Tokyo")
    check((r.second, r.microsecond) == (33, 123456), f"got {r.second}s {r.microsecond}µs")
add(C, "Seconds and microseconds preserved", _precision)


# ═════════════════════════════════════════════════════════════════════════════
# 4. WITHIN THE SAME TIME ZONE  (+ inputs that already carry a zone)
# ═════════════════════════════════════════════════════════════════════════════
C = "4. Same zone & zone-aware input"
for zone in ["Europe/Amsterdam", "UTC", "Asia/Kolkata", "America/New_York"]:
    def _identity(zone=zone):
        r = convert_timezone(MEETING, zone, zone)
        check(wall(r) == wall(MEETING), f"wall clock changed to {wall(r)}")
        check(r.tzinfo == ZoneInfo(zone), f"tzinfo is {r.tzinfo}, expected {zone}")
    add(C, f"{zone} -> {zone} leaves wall clock unchanged", _identity)


def _same_zone_dst():
    r = convert_timezone(datetime(2026, 7, 1, 12, 0), "Europe/Amsterdam", "Europe/Amsterdam")
    check(wall(r) == (2026, 7, 1, 12, 0) and r.tzname() == "CEST", f"got {wall(r)} {r.tzname()}")
add(C, "Same zone in summer keeps CEST", _same_zone_dst)

# Extra coverage: previously only one test noticed when aware input was relabelled
expect_wall(C, "Aware Tokyo 22:57, from/to Amsterdam -> converted to 14:57",
            datetime(2026, 11, 2, 22, 57, tzinfo=ZoneInfo("Asia/Tokyo")),
            "Europe/Amsterdam", "Europe/Amsterdam", (2026, 11, 2, 14, 57))
expect_wall(C, "Aware UTC 13:57 (from_tz says Amsterdam) -> New York 08:57",
            datetime(2026, 11, 2, 13, 57, tzinfo=timezone.utc),
            "Europe/Amsterdam", "America/New_York", (2026, 11, 2, 8, 57))
expect_wall(C, "Aware fixed offset +05:30 -> UTC",
            datetime(2026, 11, 2, 19, 27, tzinfo=timezone(timedelta(hours=5, minutes=30))),
            "Asia/Kolkata", "UTC", (2026, 11, 2, 13, 57))
expect_wall(C, "Aware input whose zone disagrees with from_tz across a date change",
            datetime(2026, 11, 3, 7, 30, tzinfo=ZoneInfo("Asia/Tokyo")),
            "America/New_York", "Europe/Amsterdam", (2026, 11, 2, 23, 30))


def _alias():
    try:
        ZoneInfo("US/Eastern")
    except ZoneInfoNotFoundError:
        raise SkipCase("legacy alias 'US/Eastern' not in this tz database")
    a = convert_timezone(MEETING, "Europe/Amsterdam", "US/Eastern")
    b = convert_timezone(MEETING, "Europe/Amsterdam", "America/New_York")
    check(wall(a) == wall(b), f"{wall(a)} != {wall(b)}")
add(C, "Alias US/Eastern == America/New_York", _alias)


# ═════════════════════════════════════════════════════════════════════════════
# 5. ERRONEOUS INPUTS
# ═════════════════════════════════════════════════════════════════════════════
C = "5. Erroneous inputs"
for bad in ["Mars/Olympus_Mons", "Europe/Amsterdm", "europe/amsterdam", "PST", "Amsterdam"]:
    expect_raises(C, f"Unknown source zone {bad!r}", (MEETING, bad, "UTC"), ZoneInfoNotFoundError)
    expect_raises(C, f"Unknown target zone {bad!r}", (MEETING, "UTC", bad), ZoneInfoNotFoundError)
for bad in ["", "../../etc/passwd", "/Europe/Amsterdam"]:
    expect_raises(C, f"Malformed zone key {bad!r}", (MEETING, bad, "UTC"), ValueError)
for bad in [None, 1, 3.5, ["Europe/Amsterdam"]]:
    expect_raises(C, f"Non-string zone {bad!r}", (MEETING, bad, "UTC"), TypeError)
for bad, label in [("2026-11-02 14:57", "string"), (1762091820, "Unix timestamp"),
                   (None, "None"), (date(2026, 11, 2), "date only"), (time(14, 57), "time only")]:
    expect_raises(C, f"Time given as {label}", (bad, "Europe/Amsterdam", "UTC"),
                  TypeError, AttributeError)
expect_hm(C, "Trap: Etc/GMT+1 means UTC-1 (12:00 UTC -> 11:00)",
          datetime(2026, 11, 2, 12, 0), "UTC", "Etc/GMT+1", (11, 0))


# ═════════════════════════════════════════════════════════════════════════════
# 6. GENERAL PROPERTIES (every zone pair x sample times)
# ═════════════════════════════════════════════════════════════════════════════
C = "6. General properties"
ZONES = ["UTC", "Europe/Amsterdam", "America/New_York", "Asia/Kolkata",
         "Australia/Sydney", "Pacific/Kiritimati", "Africa/Addis_Ababa"]
SAMPLES = [datetime(2026, m, 15, h, 0) for m in (1, 4, 7, 10) for h in (0, 12, 23)]


def _make_property_case(from_tz, to_tz):
    def run():
        for src in SAMPLES:
            r = convert_timezone(src, from_tz, to_tz)
            check(r == src.replace(tzinfo=ZoneInfo(from_tz)), f"{src}: instant changed")
            check(r.tzinfo == ZoneInfo(to_tz), f"{src}: tzinfo is {r.tzinfo}")
            back = convert_timezone(r, to_tz, from_tz)
            check(wall(back) == wall(src), f"{src}: round trip gave {wall(back)}")
    return run


for f in ZONES:
    for t in ZONES:
        add(C, f"{f} <-> {t}: same instant, target tz, round trip", _make_property_case(f, t))


# ═════════════════════════════════════════════════════════════════════════════
# Runner & report
# ═════════════════════════════════════════════════════════════════════════════
def run_all() -> list[Result]:
    results = []
    for case in CASES:
        try:
            case.run()
            results.append(Result(case, "PASS"))
        except SkipCase as e:
            results.append(Result(case, "SKIP", str(e)))
        except AssertionError as e:
            results.append(Result(case, "FAIL", str(e)))
        except Exception as e:
            tb = traceback.extract_tb(e.__traceback__)[-1]
            results.append(Result(case, "ERROR", f"{type(e).__name__}: {e} (line {tb.lineno})"))
    return results


def report(results: list[Result], verbose: bool, color: bool, elapsed: float) -> int:
    paint = {
        "PASS": "\033[32m", "FAIL": "\033[31m", "ERROR": "\033[35m",
        "SKIP": "\033[33m", "HEAD": "\033[1;36m", "DIM": "\033[2m", "END": "\033[0m",
    } if color else {k: "" for k in ("PASS", "FAIL", "ERROR", "SKIP", "HEAD", "DIM", "END")}
    icon = {"PASS": "✔", "FAIL": "✘", "ERROR": "!", "SKIP": "○"}

    def c(kind, text):
        return f"{paint[kind]}{text}{paint['END']}"

    print(c("HEAD", "\n══ convert_timezone() test report ══\n"))
    categories = list(dict.fromkeys(r.case.category for r in results))
    for cat in categories:
        rs = [r for r in results if r.case.category == cat]
        n_pass = sum(r.status == "PASS" for r in rs)
        tally = f"{n_pass}/{len(rs)} passed"
        colour = "PASS" if n_pass == len(rs) else ("SKIP" if all(
            r.status in ("PASS", "SKIP") for r in rs) else "FAIL")
        print(f"{c('HEAD', cat):<50} {c(colour, tally)}")
        for r in rs:
            if r.status == "PASS" and not verbose:
                continue
            line = f"   {c(r.status, icon[r.status] + ' ' + r.status):<8} {r.case.name}"
            print(line)
            if r.detail:
                print(c("DIM", f"            ↳ {r.detail}"))
    totals = {s: sum(r.status == s for r in results) for s in ("PASS", "FAIL", "ERROR", "SKIP")}
    print()
    print("Total: " + "  ".join(c(s, f"{totals[s]} {s.lower()}") for s in totals)
          + c("DIM", f"   ({len(results)} cases in {elapsed:.2f}s)"))
    ok = totals["FAIL"] == 0 and totals["ERROR"] == 0
    print(c("PASS", "\nALL TESTS PASSED ✔\n") if ok else c("FAIL", "\nSOME TESTS FAILED ✘\n"))
    return 0 if ok else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Test convert_timezone()")
    parser.add_argument("-v", "--verbose", action="store_true", help="list passing cases too")
    parser.add_argument("--no-color", action="store_true", help="disable ANSI colours")
    args = parser.parse_args()
    start = _time.perf_counter()
    results = run_all()
    return report(results, args.verbose, color=not args.no_color and sys.stdout.isatty(),
                  elapsed=_time.perf_counter() - start)


if __name__ == "__main__":
    sys.exit(main())
