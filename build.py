#!/usr/bin/env python3
"""Build schedule.js from UBC Scientia (SWS) *list-view* location timetable exports.

Usage:
    python build.py            # reads raw/*.htm, writes schedule.js
    python build.py --check    # parse + report only, don't write

How to refresh the data (needs CWL login):
    1. Open https://sws-van.as.it.ubc.ca/sws_2026/  ->  Locations tab
    2. Select the MCLD rooms (see ROOMS below), weeks "All", Type = *List*
    3. Save the page (Ctrl+S, "Webpage, Complete") into raw/
       - any number of files is fine; rows are de-duplicated across files
       - delete stale files from raw/ first if the timetable year changed
    4. python build.py
    5. git commit -am "refresh schedule" && git push

Only the standard library is used, so this runs anywhere Python 3.8+ exists.
"""
import datetime as dt
import glob
import html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
RAW_DIR = os.path.join(HERE, "raw")
OUT_FILE = os.path.join(HERE, "schedule.js")

# Rooms the site cares about. Rows for any other location (multi-room events
# often list LIFE/MCML rooms too) are dropped.
ROOMS = [
    "MCLD 2002", "MCLD 2012", "MCLD 2014", "MCLD 2018",
    "MCLD 3002", "MCLD 3008", "MCLD 3014", "MCLD 3018",
]

DAY_INDEX = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}

HEADER_RE = re.compile(
    r'header-0-0-1">([^<]*)</span>.*?header-0-0-3">([^<]*)</span>.*?header-0-0-5">([^<]*)</span>',
    re.S,
)
DAY_TABLE_RE = re.compile(r'<span class="labelone">(\w+)</span></p>\s*(<table.*?</table>)', re.S)
ROW_RE = re.compile(r"<tr>(.*?)</tr>", re.S)
CELL_RE = re.compile(r"<td>(.*?)</td>", re.S)
TAG_RE = re.compile(r"<.*?>")


def parse_weeks(spec):
    """'3-7, 9-16' -> [3,4,5,6,7,9,...,16]"""
    weeks = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-")
            weeks.extend(range(int(a), int(b) + 1))
        else:
            weeks.append(int(part))
    return sorted(set(weeks))


def parse_time(s):
    """'9:30' -> 570 (minutes after midnight)"""
    h, m = s.strip().split(":")
    return int(h) * 60 + int(m)


COURSE_RE = re.compile(r"^([A-Z]+)_V\s+(\S+?)-W/(\w+)/(\S+)$")


def short_name(name):
    """Compact display name.
    'CPSC_V 121-W/DIS/T1F'                                  -> 'CPSC 121 DIS'
    'T1 Mon B Monday (week(s): Aug 31, ...) 16:00 - MCLD 3018' -> 'T1 Mon B Monday'
    """
    m = COURSE_RE.match(name)
    if m:
        return f"{m.group(1)} {m.group(2)} {m.group(3)}"
    s = re.sub(r"\s*\(week\(s\):.*?\)", "", name)          # (week(s): ...)
    s = re.sub(r"\s+\d{1,2}:\d{2}\s*-\s*[A-Z]{2,5} .*$", "", s)  # ' 16:00 - MCLD 3018, ...'
    s = re.sub(r"\s+\d{1,2}-[A-Z][a-z]{2}-\d{4}$", "", s)     # trailing '12-Jun-2027'
    s = re.sub(r"\s+\d{1,2}-[A-Z][a-z]{2}-\d{4}\s+", " ", s)
    s = re.sub(r"\s+(Mon|Tue|Wed|Thu|Fri|Sat|Sun)(,\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun))*$", "", s)
    return re.sub(r"\s{2,}", " ", s).strip() or name


def parse_date(s):
    """'08/24/26' or '08/24/2026' -> date"""
    m, d, y = (int(x) for x in s.split("/"))
    if y < 100:
        y += 2000
    return dt.date(y, m, d)


def parse_file(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    hm = HEADER_RE.search(text)
    if not hm:
        raise ValueError(f"{path}: no 'Exported Weeks' header found - is this a list-view export?")
    weeks_span, start, end = (html.unescape(x).strip() for x in hm.groups())
    week1 = parse_date(start)
    rows = []
    for day, table in DAY_TABLE_RE.findall(text):
        for tr in ROW_RE.findall(table):
            cells = [html.unescape(TAG_RE.sub("", c)).strip() for c in CELL_RE.findall(tr)]
            if len(cells) != 11 or cells[0] == "Name":
                continue
            name, section, typ, dept, weeks, location, staff, module, _days, t0, t1 = cells
            rows.append({
                "room": location,
                "day": DAY_INDEX[day],
                "start": parse_time(t0),
                "end": parse_time(t1),
                "weeks": weeks,
                "name": name,
                "type": typ,
                "staff": staff,
            })
    if not rows:
        raise ValueError(f"{path}: header found but zero activity rows")
    return week1, weeks_span, parse_date(end), rows


def main(check_only=False):
    files = sorted(glob.glob(os.path.join(RAW_DIR, "*.htm")) + glob.glob(os.path.join(RAW_DIR, "*.html")))
    if not files:
        sys.exit(f"No .htm/.html files in {RAW_DIR}")

    week1 = None
    export_end = None
    merged = {}   # dedupe key -> event
    per_file = {}
    for f in files:
        w1, span, end, rows = parse_file(f)
        if week1 is None:
            week1, export_end = w1, end
        elif w1 != week1:
            sys.exit(f"Week-1 date mismatch: {os.path.basename(f)} starts {w1}, others start {week1}. "
                     f"Mixed timetable years in raw/ - delete the stale ones.")
        kept = 0
        for r in rows:
            if r["room"] not in ROOMS:
                continue
            key = (r["room"], r["day"], r["start"], r["end"], r["weeks"], r["name"])
            ev = merged.setdefault(key, {**r, "staff": []})
            if r["staff"] and r["staff"] not in ev["staff"]:
                ev["staff"].append(r["staff"])
            kept += 1
        per_file[os.path.basename(f)] = (len(rows), kept)

    if week1.weekday() != 0:
        sys.exit(f"Week 1 start {week1} is not a Monday - export header parsed wrong?")

    events = []
    for ev in merged.values():
        if ev["end"] <= ev["start"]:
            print(f"WARNING: dropping zero/negative-length event {ev}", file=sys.stderr)
            continue
        events.append({
            "room": ev["room"],
            "day": ev["day"],
            "start": ev["start"],
            "end": ev["end"],
            "weeks": parse_weeks(ev["weeks"]),
            "name": ev["name"],
            "short": short_name(ev["name"]),
            "type": ev["type"],
            "staff": ", ".join(ev["staff"]),
        })
    events.sort(key=lambda e: (e["room"], e["day"], e["start"], e["end"], e["name"]))

    # Latest file mtime = when the export was taken (good enough for the banner).
    exported = max(dt.datetime.fromtimestamp(os.path.getmtime(f)) for f in files)

    counts = {room: sum(1 for e in events if e["room"] == room) for room in ROOMS}
    print(f"week 1 starts {week1} (Mon), export covers through {export_end}")
    for name, (total, kept) in per_file.items():
        print(f"  {name}: {total} rows, {kept} in tracked rooms")
    print(f"{len(events)} unique events:")
    for room, n in counts.items():
        flag = "  <-- NO EVENTS, missing export?" if n == 0 else ""
        print(f"  {room}: {n}{flag}")
    missing = [r for r, n in counts.items() if n == 0]
    if missing and not check_only:
        sys.exit("Refusing to write schedule.js with empty rooms. Export them or remove them from ROOMS.")

    if check_only:
        return

    data = {
        "generated": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "exported": exported.strftime("%Y-%m-%d"),
        "week1": week1.isoformat(),
        "exportEnd": export_end.isoformat(),
        "rooms": ROOMS,
        "events": events,
    }
    with open(OUT_FILE, "w", encoding="utf-8") as fh:
        fh.write("// Generated by build.py - do not edit by hand.\n")
        fh.write("window.SCHEDULE = ")
        json.dump(data, fh, separators=(",", ":"), ensure_ascii=False)
        fh.write(";\n")
    print(f"wrote {os.path.relpath(OUT_FILE, HERE)} ({os.path.getsize(OUT_FILE)//1024} KB)")


if __name__ == "__main__":
    main(check_only="--check" in sys.argv)
