# Code maps

Measurements of this repository taken by parallel readers before a large change,
kept because the reading cost more than the writing did.

**These are dated snapshots, not documentation.** Every `file:line` in them was
true on the day named in the filename and starts going stale with the next edit.
Read them for the *reasoning* — which symbols are shared, which guard protects
what, why an arrangement is the way it is — and re-verify any specific line
before acting on it.

They are not maintained. A map that is wrong and looks maintained is worse than
no map, so nothing here is updated in place: when the ground moves enough to
matter, a new dated map is written and the old one is left alone as a record of
what was true then.

## What is here

| Map | Taken before | Why it was worth keeping |
|---|---|---|
| [2026-08-11-drive-bridge.md](2026-08-11-drive-bridge.md) | Moving Drive into the panel (#164) | Established that `extension/bundleview.js` had no caller at all, that no engine route accepted a Google token, and that `scrapex/gdrive.py` was a **second** Google identity carrying the sensitive `spreadsheets` scope beside the panel's non-sensitive three. |
| [2026-08-11-google-removal.md](2026-08-11-google-removal.md) | Deleting the engine's Google surface | Its most valuable column is `keep`. `SheetSink`, `publish_source`, `workbook_tables`, `_about` and `_sink_batch` all *look* like Google code and all serve the **local Excel** path; deleting them alongside the Google ones would take a working feature with them — including silently restoring the four-full-workbook-rewrites bug fixed in `0a2209c`. |

## Why they exist at all

The pattern recorded in `BACKLOG.md` §6b — a guard that checks something is
*declared* rather than that it *works* — has a twin in reading: a claim about the
code that was never measured. Several corrections in this project came from
someone finally opening the file, and more than one of those claims was mine.

A map does not prevent that. It only makes the measurement worth doing once.
