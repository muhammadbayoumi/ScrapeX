# ScrapeX UI surfaces

ScrapeX has two complementary interfaces over the same local engine:

- the Chrome side panel is the always-available, compact remote control;
- the web workspace owns deep tables, configuration, and guarded operations.

They share navigation and run-mode metadata from `scrapex/ui_manifest.py`. The
workspace renders that module directly and the panel consumes `/api/ui`. Visual
tokens have one source in `extension/tokens.css`; `tools/sync_ui_assets.py`
generates the packaged web copy and a test rejects drift.

## Capability parity

| Capability | Side panel | Web workspace | Why the presentation differs |
|---|---|---|---|
| Add and inspect sources | Current tab, URL batch, and Add Site | Add/manage form | Current-tab access requires Chrome APIs. |
| Start collection jobs | Native compact controls | Native launcher on Jobs | Both consume the same run modes and `/api/jobs`. |
| Monitor jobs and logs | Live mini-player and bounded log tail | Jobs table and full Logs page | The panel stays useful at 320px; the workspace has room for history. |
| Browse saved data | Compact dataset and record browser | Full tables, fields, and saved views | Both read the same bounded APIs. |
| Changes, history, and review | Shared workspace links | Native pages | Deep tables are opened from the panel, not duplicated inside it. |
| Schedules | Compact status summary | Full Schedules page | Scheduling remains owned by the local engine. |
| Sync and exports | Status plus shared workspace links | Full setup and action pages | Configuration has one owner to prevent drift. |
| Runtime and settings | Status plus safe summaries and links | Full settings sections | The panel remains a remote control, not a second settings implementation. |
| Storage repair/restore/move | Read-only summary and link | Guarded controls | Destructive actions are deliberately kept away from a browsing panel. |

Adding a workspace destination or changing run-mode copy starts in
`scrapex/ui_manifest.py`. Do not hand-add the same item to either navigation.
Browser-only capabilities may remain panel-only; guarded or table-heavy
capabilities may remain workspace-owned as long as the panel exposes their
shared destination.
