# The engine lives on the Engine page — `REQ-50`

**Written 2026-08-30, on branch `claude/scrapex-engine-consolidation-d69e0a`.** Governed by
[R-80](../RULINGS.md#r-80--one-feature-one-place-and-a-read-only-second-copy-is-still-a-second-copy)
(one feature, one place — display is not an exemption),
[R-48](../RULINGS.md#r-48--the-extension-is-the-control-room-and-the-only-interface-the-engine-executes-and-reports)
and [R-50](../RULINGS.md#r-50--the-engine-is-a-helper-to-the-extension-and-any-task-the-extension-can-do-moves-to-it).

**Batch 1 is built on this branch. This plan exists for batch 2**, which is blocked on a
decision, and for whoever picks the rest up — the owner approved the split in his own words:
«اوافق على 1».

---

## What "the Engine page" means

`#view-engine-detail` in `extension/app.html` — the screen reached from the engine row, not
`#view-engines` (the catalogue) and not a source file. He corrected this himself: *«اقصد
بصفحة engine هذه الصفحة فى الصور لا اقصد file فى الكود»*.

## Batch 1 — done

| | what | why it needed no ruling |
|---|---|---|
| 1 | delete `restartEngineFromPanel` and `#engine-restart` | it is a strict subset of the survivor: no preflight, no poll, no button disabling, and it ends by announcing a success it never checked |
| 2 | move `#runtime-restart` into `#engine-action-list`, id unchanged | three guards read that id as a literal; renaming would have made a layout change look like a capability change |
| 3 | messages reach BOTH screens, and the reason travels | four sentences end in *"the reason is shown above"* — true in Settings beside `#runtime-error`, false on a screen with no card |
| 4 | confirmation budget 30 s to 125 s | derived from `relaunch.py`'s own 30 + 90 and the 1.5 s bow-out, not chosen |
| 5 | `schema_lag` carried across `checkEngine` | `OP-113` |
| 6 | `.engine-spec-note` becomes `display: contents` | `OP-114`; the columns are not touched, so the defect the old comment defends against cannot return |
| 7 | the engine's own page stops polling a deleted route | `OP-112` |
| 8 | `tools/engine_verify.py` gains the stale-build capture | the state that hid `OP-114` from every screenshot ever taken |

## Batch 2 — the power switch, and what blocks it

He asked for it plainly: *«اريد Engine power حيث ايقافه ثم تشغيله تعنى restart · اذا يكون
لدينا زرين ايقاف وزر ريسترت»*.

**The ON half is already built.** `START_ENGINE` is a native-messaging command
(`scrapex/native.py`), idempotent by probe rather than by bookkeeping, and the panel already
sends it from `#engine-start` on the Run view. It **must** stay native: an engine that is
down cannot serve the request to start itself.

**The OFF half exists in no form** — no route, no native command, no CLI subcommand.

### The blocker, stated so it can be lifted rather than rediscovered

`POST /api/engine/stop` moves the endpoint fingerprint, and
`tests/test_the_version_moves_when_the_contract_does.py` fails when that moves while
`VERSION` stays. [R-77](../RULINGS.md#r-77--one-number-one-question-the-extension-carries-the-version-the-engine-carries-a-protocol-and-a-build)
— merged the same day — says the engine has no marketing version and that `VERSION` stops
being hand-edited. **The ruling is in force; the gate has not been rebuilt.** So the route
lands only after either that work or his word. Do not bump to get past it: that is exactly the
churn `R-77` exists to end.

### The design, measured

**Stop is not a mirror of restart.** Restart spawns a detached helper and exits, because a
process cannot free its own port and re-bind it. Stop needs no successor, so it is the same
shape minus the helper — **but it must drain first rather than mirror `os._exit(0)`.**

A hard kill is *safe*: `jobs.reclaim_orphaned_jobs` re-queues anything left `running` at the
next start, and `tests/test_the_engine_survives_being_killed.py` kills a real engine mid-crawl
with `Popen.kill()` and proves the row does not stay stuck. What a kill *costs* is the journal
for the source in flight — `capture.py` clears it, because a connector that cannot skip cannot
resume — so the crawl re-runs that source from the top. On a 3,874-product source behind a
10 s crawl delay that is an eleven-hour crawl discarded and immediately re-spent. Pausing the
job first writes the checkpoint that makes the resume cheap.

**What a stop must refuse**, each with a reason a person can act on:

- a bundle build in flight — it cannot be interrupted without leaving a broken archive, which
  is `OP-100` in its other costume;
- the warehouse write lock held by this process;
- a running crawl **without** confirmation — refuse once with a header the panel reads, and
  let the second flip confirm. A switch that refuses to switch is not a switch.

A crawl run by a **separate** process (`scrapex contractors`) cannot be stopped by this route
and must be named in the answer, or *"Engine power: off"* is a lie.

**What the switch must not be bound to.** `state.engineUp` is `worker_alive`, a 30-second
heartbeat — not whether the process exists. A switch bound to it reads OFF for a running
engine, and turning it "on" then sends `START_ENGINE`, which probes the port, answers
`already_running`, and does nothing; the switch flips back with nothing said.

**Unmeasured, and worth measuring before wiring:** whether a Windows Startup entry or a
Scheduled Task can bring the engine back on its own. If one can, the switch will appear to
flip itself back on, and either the OFF path disables it or the disclosure says so.

## Batch 3 — the rest of the surface, not started

`R-80` covers the whole product; this branch covers the engine. Measured and left:

- **31 live routes reachable only from the engine's own pages**, of which nine are storage
  (backup, restore, move, compact, repair, start-fresh, export, open-folder) and four are
  retention. `MIGRATION-PLAN`'s **B3** owns them, and its rule is that the typed confirmations
  and the disabled-until-valid interlocks are safety, so **safety moves with the control or
  not at all**.
- **Eight settings changeable nowhere but the web UI**, across three templates —
  `backup_folder`, five `excel_*`, and two `funnel_*`.
- **The whole update subsystem has no caller anywhere** — `GET/POST /api/update` and
  `/api/update/plan`, mounted unconditionally, while the panel reimplements the release check
  in JavaScript and its own comment admits it cannot verify the SHA-256.
- **Two guards must be repaired before this batch, not after.** `_control_ids` cannot see a
  `<button>`, so the rule it enforces is unenforced; and
  `test_the_web_page_still_shows_what_the_engine_holds` asserts the display-only concession
  `R-80` retracted. Whichever change first moves a value off the web page owns both.

## Open, and his

**What the version rows say.** `Installed version` and `Latest version` on the Engine page
answer a question `R-77` says the engine no longer has, and `Latest version` is `R-07`'s
advert in a second costume. `Protocol` and `Build` are promoted by the same ruling.
**Recommendation: keep `Build` and `Protocol`, delete the other two** — `Build` names the tree
exactly, while one version string is shared by ten distinct commits. Not taken here, because
it changes what he reads.
