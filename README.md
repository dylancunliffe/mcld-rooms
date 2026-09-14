# MacLeod free rooms

A static site that shows which MacLeod (MCLD) classrooms at UBC are free right now, for how long,
and when the busy ones open up. Built for finding a study spot.

Live page: `https://<your-github-username>.github.io/mcld-rooms/` (after enabling Pages, below).

## How it works

- `raw/*.htm` - list-view exports from the UBC Scientia room timetable (needs CWL to access).
- `build.py` - parses them into `schedule.js` (the only data file the page loads).
- `index.html` - the site. Pure HTML/JS, no build step, no dependencies. Works from `file://` too.

Rooms covered: MCLD 2002, 2012, 2014, 2018, 3002, 3008, 3014, 3018 (the general-purpose classrooms;
the other MCLD rooms are labs).

## Refreshing the schedule

Ad-hoc bookings get added throughout the term, so re-export every week or two:

1. Log in at <https://sws-van.as.it.ubc.ca/sws_2026/> and open the **Locations** tab.
2. Select the MCLD rooms above, weeks **All**, and set the view type to **List** (not Grid).
3. Save the page (Ctrl+S, "Webpage, Complete") into `raw/`. Several files are fine - rows are
   de-duplicated across files, so one export per room or one big export both work.
   If the timetable year has rolled over, delete the old files from `raw/` first.
4. Run:

   ```bash
   python build.py
   ```

   It prints the week-1 date, per-room event counts, and refuses to write if a room has no events
   (usually means an export is missing). `python build.py --check` reports without writing.
5. Commit and push:

   ```bash
   git add -A && git commit -m "refresh schedule" && git push
   ```

The page footer shows the export date so users know how fresh the data is.

## Publishing on GitHub Pages

1. Create a GitHub repo called `mcld-rooms` and push this folder to it.
2. Repo **Settings -> Pages -> Build and deployment**: Source = *Deploy from a branch*,
   Branch = `main`, folder = `/ (root)`. Save.
3. The site appears at `https://<username>.github.io/mcld-rooms/` within a minute or two.

## Notes / caveats

- Free = no timetabled booking. It doesn't know about walk-in use or bookings made after the export.
- Room access isn't modelled. (3rd-floor rooms lock at 17:00 and all rooms lock at 23:00; if you
  ever want that shown, it's a small addition to `index.html`.)
- Week numbers in the export are relative to the timetable's week 1 (Monday of the first exported week);
  `build.py` reads that date from the export header, so nothing needs hand-editing when the year changes.
- Times are computed in `America/Vancouver` regardless of the visitor's timezone.
