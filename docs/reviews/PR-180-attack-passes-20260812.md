# PR #180 — the five attack passes, unverified

**Raised 2026-08-12. NOT VERIFIED.** The eight sceptics that would have
tried to refute these all died on a session limit, so nothing below has
survived a challenge. Recurrence across independent lenses is evidence,
not proof. Kept because the passes cost 761k tokens and would otherwise
be lost.


## ?

### [high] Under prefers-reduced-motion the checking screen has no signal at all that anything is happening

`extension/app.css:3085`

**Failure:** A user with "Reduce motion" on (Windows "Show animations: Off", macOS Reduce Motion) opens the side panel while Chrome's non-interactive token check is in flight. The sweep is stopped twice over — by this rule's `animation: none` and, independently, by the pre-existing blanket `animation-duration: 0.01ms !important; animation-iteration-count: 1 !important` on `*` at extension/components.css:951-959. So the thumb is parked at the start edge and never moves. Every other element in the state is static: the 96px mark, "ScrapeX", "where everything begins". The one sentence that stated the wait, "Checking your account…", is now `visually-hidden` (extension/app.html:1130). The result is a frozen screen with no words and no motion — visually indistinguishable from a panel that failed to load — for as long as the check takes (seconds, when Chrome identity is slow or the machine is offline). On origin/main the same user read "Checking your account…". The PR's own comment says a stalled-looking thumb "is the opposite of what this screen is for"; parking it at the start edge is equally stalled, because motion was the only carrier left.

**Proposed:** Motion cannot be the sole carrier of this state. Restore the sentence to the screen when motion is off. This cannot be done with a media query while the class stays in the markup — `.visually-hidden` sets all eight properties with `!important` (extension/components.css:167-177) and nothing can override it. So drop `visually-hidden` from the `<p class="profile-status">` at extension/app.html:1130 and clip it from app.css instead: `#welcome-checking .profile-status { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }` and then, inside the existing reduced-motion block, `#welcome-checking .profile-status { position: static; width: auto; height: auto; clip: auto; white-space: normal; }`.

### [high] The role=status live region the PR names as its justification is never written to, and is display:none at the moment the outcome lands

`extension/app.html:1130`

**Failure:** The comment above this line justifies keeping the hidden paragraph on the grounds that deleting it "would leave a screen-reader user in silence while the panel decides who they are." That mechanism does not exist. `git grep profile-status` on the branch returns only extension/app.css:1281, this line, and the diagnostic copy — no JavaScript writes it. "Checking your account…" is static initial content, present in the file before any script runs, and a live region only announces mutations made after it is registered. NVDA/VoiceOver therefore announce nothing on panel open. There is also no announcement when the wait ends: `setChecking(false)` (extension/app.js:2252-2264) only flips `aria-busy`, toggles `.hidden`, and rewrites `#tab-profile`'s aria-label — none of which speaks on an unfocused element. So a screen-reader user reading the opening frame has the content silently swapped out from under the virtual cursor and is never told the check finished. The PR compounds this: the string it kept "for the announcement" is now spoken by nobody and seen by nobody, reachable only by manually browsing the buffer. Note this is also structurally unfixable in place: because `#welcome-checking` gets `display: none` (extension/components.css:179) in the same frame the outcome arrives, a live region nested inside it is removed from the accessibility tree at exactly the moment it would need to speak.

**Proposed:** Either drive the region from app.js or stop claiming it announces. If keeping it: move the live region out of `#welcome-checking` to a sibling of the three states inside `#profile-card` (so it survives the toggle), give it an id, and have `setChecking()` write "Checking your account…" on entry and the outcome ("Signed in as …" / "Not signed in") on exit. If not keeping it: delete the paragraph and rewrite the comment, since the checklist item it cites is not satisfied by static markup.

### [medium] In Windows High Contrast the checking state loses the bar and the mark, and the text that used to survive is now clipped

`extension/app.css:1245`

**Failure:** A user in forced-colors mode (Windows High Contrast) opens the panel. Forced colors overrides author `background-color` to the system Canvas colour, so `.checking-bar { background: var(--line) }` and `.checking-bar-thumb { background: var(--accent) }` both render as Canvas-on-Canvas and disappear; the same happens to `#welcome-checking .welcome-mark { background: var(--accent) }` at line 1218, which is a mask painted entirely by its background. The existing forced-colors block at extension/components.css:962-974 targets only button/.button/.card/.banner/.chip/.badge/input/select/textarea, so nothing restores any of them. What remains on screen is "ScrapeX" and "where everything begins" on blank canvas, with zero indication a wait is in progress. This is a regression: forced colors preserves text, so on origin/main this same user read "Welcome to ScrapeX" and "Checking your account…". The PR converted the state's only information from text into a background-painted graphic and clipped the text away.

**Proposed:** Add a forced-colors rule for the new bar, alongside the reduced-motion one: `@media (forced-colors: active) { .checking-bar { border: 1px solid CanvasText; background: Canvas; } .checking-bar-thumb { background: Highlight; forced-color-adjust: none; } }`. The text fix from the reduced-motion finding (un-clipping `.profile-status`) also covers this case and is the more robust of the two.

### [medium] Light theme: the sole visible activity indicator is a 3px graphic at 2.56:1, below the 3:1 non-text minimum

`extension/app.css:1256`

**Failure:** In the light theme (`--bg: #f5f7f9`, extension/tokens.css:21), the thumb is `--accent: #00adb5` (tokens.css:33). Computed contrast against the page background the PR just exposed by setting `background: transparent` on the card at line 1207 is 2.56:1 — under the 3:1 that WCAG 1.4.11 requires of a graphical object needed to understand the content, and the bar now IS that object, since the status sentence is hidden. The track is worse: `--line: #dfe3e8` on `#f5f7f9` is 1.20:1, effectively invisible. So a low-vision or low-contrast-display user in light mode sees a faint 40px teal dash sliding across nothing, 3px tall, with no text anywhere saying what it means. Dark mode is fine (`#35c8ce` on `#0f1216` = 9.21:1), so this reproduces only in light. The bar was designed against the card surface it no longer sits on.

**Proposed:** Paint the thumb with `--accent-ink` (#006b70 light) rather than `--accent` — that measures 5.86:1 on `--bg` and keeps the brand hue — and raise the track to `--line-strong` (#c5cbd3) so the two read apart. Increasing the 3px height helps perception but does not change the ratio, so the colour swap is the actual fix.


## ?

### [high] Sweep keyframe travels to 10rem while the track clamps to 100%, blanking the bar for up to a third of every cycle

`extension/app.css:1271`

**Failure:** `.checking-bar` is `width: var(--checking-track)` (10rem) with `max-width: 100%`, but the keyframe travels `inset-inline-start` from `-2.5rem` to a hard `var(--checking-track)`. When max-width wins, the thumb is only inside the visible track for `(W + thumb)` of the `(10rem + thumb)` distance, so the fraction of each 1.4s cycle showing anything is `(W + 2.5rem) / 12.5rem`. Available width = panelWidth - rail - 2*sp4 - 2*sp5, and `rem` follows Chrome's font-size setting because `html` sets no font-size (components.css:21). At Chrome "Very large" font (24px root) the track wants 240px but gets `panel - 204`, so it clamps below a 444px panel - i.e. at every realistic side-panel width. At 400px wide: W=196px, thumb=60px, travel=300px, so the track is completely empty for 44/300 = 14.7% of the cycle = 0.21s. At 360px: 0.39s. At 320px (rail 3.25rem, main padding sp-3): W=134px, empty 0.49s of every 1.4s. The owner sees the loading bar visibly stall and restart - exactly what the PR's own reduced-motion comment at app.css:3082 says must not happen ("reads as stalled - as if the wait had failed"). At "Large" font (20px) it clamps below 370px, so the repo's own 360px test width is already affected.

**Proposed:** Make the travel a percentage so it follows the rendered width instead of the requested one: `to { inset-inline-start: 100%; }` at app.css:1271. `inset-inline-start` percentages resolve against the containing block's inline size (the bar's padding box), so a clamped track and its keyframe can no longer drift apart, and `--checking-track` goes back to setting `width` only. Separately, `padding: var(--sp-5)` at app.css:1205 costs 48px of that width for no visual purpose - `main` and `#view-profile` already inset the page, and the sibling signed-in rule at app.css:1450 uses `padding: 0`.

### [medium] The :has() rule copies the signed-in reset but omits `justify-content: flex-start`, reinstating the unreachable-top-overflow trap

`extension/app.css:1200`

**Failure:** The rule sets `overflow: visible`, which makes `.profile-stage` the sole scroller - the same arrangement as the signed-in rule at app.css:1442 - but does not reset `justify-content`, so the card keeps `center` from the base rule at app.css:1181. `.profile-card` is stretched to the stage's height (align-items defaults to stretch, and `margin-block: 0` removes the auto margins that would have prevented it), and `#welcome-checking` has `flex: 1` with `min-height: auto`, so when its content exceeds the stage height the free space goes negative and `center` splits it evenly above and below. Overflow above a scroll container's block-start is not scrollable - scrollTop 0 is already the top - so the overflowing half is clipped and unreachable, which is precisely the defect the sibling rule's comment (app.css:1428-1438) documents and fixes. Content height at 24px root: mark 144 + gap 36 + name 63 + gap 24 + tagline 2 lines 59 + gap 24 + bar 3 + card padding 72 = ~425px. At the repo's own measured 400x520 with a crawl running (`.sx-mini` occupying body grid row 2), the stage is ~400px, so ~12px of the top of the 96px brand mark - the whole point of the splash - is cut off with no way to scroll to it. At 20px root the threshold is a ~370px-tall panel.

**Proposed:** Add `justify-content: flex-start;` to the rule at app.css:1200-1210, matching app.css:1450. This puts all overflow at the block-end where `.profile-stage` can scroll to it, and removes the class of failure rather than the one configuration that was found. `#welcome-checking { flex: 1 }` at app.css:1213 keeps the splash centred in the normal case, since a grown flex item centres its own children via its `justify-content: center`.

### [medium] Hiding the status line leaves the interactive sign-in wait - up to 120 seconds - showing a wordless splash

`extension/app.html:1130`

**Failure:** The HTML comment justifies hiding the status text with "this state is gone in a second". That holds only for the silent open path (getToken 2500ms + accountFor 6000ms = 8.5s worst case). app.js:5367 also calls `loadAccount({interactive: true})` from the sign-in button, and `STARTUP_DEADLINES.interactiveToken` is 120000 (extension/startup.js:7). `loadAccount` calls `setChecking(true)` at app.js:2352, which adds `.hidden` to `#welcome-signed-out` (app.js:2256) - and `#signin-status`, the paragraph the handler fills with "Signing in..." at app.js:5364, lives inside that hidden state (app.html:1158). So an owner who clicks "Sign in with Google", leaves Chrome's consent window open while fetching a password, and comes back to the panel sees a brand splash with a marketing tagline and no words about what is happening, for up to two minutes. On origin/main that same wait read "Welcome to ScrapeX / Checking your account...". The 3px bar is also animating `inset-inline-start`, which cannot be composited, so it forces a main-thread layout on every frame for that whole duration.

**Proposed:** Either keep the status sentence on screen in the checking state (drop `visually-hidden` from the `<p class="profile-status">` and style it where `.checking-tagline` sits, so the tagline is the copy for the fast path and the status replaces it when a wait is long), or do not route the interactive path through `setChecking(true)` at all - leave `#welcome-signed-out` up so its existing `#signin-status` "Signing in..." line is the thing the owner reads. The splash is only defensible for the bounded 8.5s silent check.

### [low] Under prefers-reduced-motion the thumb parks at the start edge, reading as a progress bar hung at 25%

`extension/app.css:3085`

**Failure:** The reduced-motion override sets `animation: none; inset-inline-start: 0`, leaving a 2.5rem accent segment sitting at the left of a 10rem track - a static, filled quarter of a bar. To anyone with Windows animation effects turned off (a common, non-exotic setting), that is a determinate progress bar frozen at 25%, and since the status paragraph is now `visually-hidden` (app.html:1130) there is no text on screen contradicting it. The rule's own comment argues that a frozen thumb "reads as stalled - as if the wait had failed - which is the opposite of what this screen is for", then produces a frozen thumb; moving it to the start edge changes where it is stuck, not that it looks stuck.

**Proposed:** Under reduced motion, stop drawing a bar that implies progress: `.checking-bar { display: none }` (it is already `aria-hidden`, so nothing is lost from the accessibility tree) and unhide the `.profile-status` sentence in the same media block, so the state is conveyed by the words instead of by a motionless indicator. If a visual is wanted, an opacity pulse on the full track carries "working" without implying a completed fraction.


## ?

### [medium] Under prefers-reduced-motion the checking screen shows no sign of activity at all

`extension/app.css:3085`

**Failure:** The reduced-motion block sets `.checking-bar-thumb { animation: none; inset-inline-start: 0; }`. The thumb is `--checking-thumb: 2.5rem` on a `--checking-track: 10rem` track (app.css:1246-1247), so it parks as a static bar filled to exactly 25%. In the same PR the only sentence on the screen, "Checking your account…", was moved behind `visually-hidden` (app.html:1130), and the bar itself is `aria-hidden="true"` (app.html:1114). Concrete state: a user with Windows "Show animations in Windows" off (or macOS Reduce motion) opens the side panel while the non-interactive token check is in flight — the state tests/test_panel_dom.py:2999 simulates with signin_delay_ms=1000. What they see is a static mark, the word ScrapeX, a tagline, and a quarter-filled accent bar that never moves, with no text. Nothing on the frame says work is happening; it reads as a finished screen with a stuck progress bar. Before this PR the same user read "Checking your account…". The comment on the rule argues a thumb frozen mid-track reads as stalled — parked at 25% of the track reads as stalled too, because the track is visible behind it.

**Proposed:** Under `prefers-reduced-motion: reduce`, restore a text channel rather than a frozen geometry: drop `visually-hidden` from `.profile-status` inside that media block so the sentence is on screen, or fill the track (`.checking-bar-thumb { inline-size: 100%; }`) so the bar reads as indeterminate-busy instead of 25%-complete.

### [medium] The kept-and-hidden status line cannot announce: it never mutates and sits under aria-busy="true"

`extension/app.html:1130`

**Failure:** The PR keeps `<p class="profile-status" role="status" aria-live="polite">` and hides it, on an 11-line justification that this is the live region that announces the state. Two untouched files refute that. (1) No JavaScript anywhere in extension/ ever writes `.profile-status` — grep for `profile-status` across every .js/.mjs in extension/ returns nothing. The text is static markup, and a polite live region announces on content mutation, so this one never fires on its own. (2) The author's likely fallback — Chromium announcing a status region as it becomes displayed — is cancelled by `aria-busy="true"` on the ancestor `#profile-stage` (hard-coded at app.html:1099 and re-set at app.js:2253), which tells assistive tech to withhold subtree updates. app.js:2253-2254 sets aria-busy and unhides `#welcome-checking` in the same two statements, and `setChecking(false)` clears aria-busy and hides the state together, so there is no window in which the region is both displayed and announceable. Concrete: a screen-reader user opens the panel on a slow network; nothing is spoken for the duration of the check, and the sentence that a sighted user could previously read is now clipped to 1px. The comment tells the next maintainer a safety net exists where there is none.

**Proposed:** Either make the claim true — have `setChecking(true)` write the status text so the region actually mutates, and move the region out from under the `aria-busy` ancestor (or stop setting aria-busy on an ancestor of it) — or delete the claim and keep the sentence visible.

### [low] The diagnostic twin of app.html has no guard and is already 360 lines out of step

`extension/tests/diagnostic-app-nomodule.html:26`

**Failure:** This file is hand-maintained (its own banner: regenerated by hand from app.html, so it drifts the moment app.html changes), it is absent from tools/sync_design_assets.py's ASSETS map (lines 20-71, which covers only tokens.css, components.css, appearance.js, split-button.js, timezone.js and four icon files), and no test compares it to app.html — the only non-worktree reference in the repo is extension/background.js:61, and side-panel-startup.test.mjs:527 tests the unrelated diagnostic-panel.html. Measured: after normalizing the `../` path prefixes and removing the one deliberately-dropped `<script type="module" src="app.js">` line, the twin differs from app.html by 360 lines on origin/main and 376 on this branch. Concrete: a developer double-clicks the diagnostic to answer the question it exists for — does app.js block first paint, or is it markup volume — and loads a page missing whole sections of app.html, including the entire `<section class="card" aria-labelledby="source-edit-robots-heading">` robots.txt block. "It paints" then proves nothing about app.js, because the markup volume being compared is not the same. The banner's promise of byte-for-byte equality is already false. This PR's hand-edit kept the changed block itself in step (its 16 new differing lines are all comments), but it is the second hand-edit past a missing guard.

**Proposed:** Add a test that normalizes `../` prefixes and the dropped app.js script line and asserts the two files are otherwise equal, or generate the twin from app.html in tools/sync_design_assets.py so `--check` reports it stale — then regenerate it, which will also clear the 360 pre-existing lines of drift.


## ?

### [high] Under prefers-reduced-motion the opening frame has neither motion nor words, and reads as a progress bar stalled at 25%

`extension/app.css:3085`

**Failure:** With OS "reduce motion" on (Windows "Show animations" off, macOS Reduce Motion, or battery saver), open the panel on Profile while Chrome answers. Measured at 400x700: the thumb is parked at the track's start edge, 40px of a 160px track — exactly 0.25 of it, static. Because this PR also moved "Checking your account…" into .visually-hidden (app.html:1130), there is now no other on-screen signal: the frame is a logo, the word ScrapeX, the tagline, and a motionless quarter-filled bar. That is indistinguishable from a determinate bar stuck at 25%, i.e. a failed wait — the exact reading the comment above the rule says it is avoiding. It is worse in light mode: the track is var(--line) at 1.44:1 against the page background (the card is now background:transparent, so the bar sits on --bg, not --surface), so the track is effectively invisible and the parked thumb does not even read as part of a bar — it is a lone 40px dash. Before this PR the same user read "Checking your account…" in plain text.

**Proposed:** Reduced motion must not remove the only status signal. In the @media (prefers-reduced-motion: reduce) block, hide .checking-bar and give the sentence back — e.g. toggle the visually-hidden class off .profile-status there (it needs !important-strength overrides, so the clean form is a state class on #welcome-checking rather than fighting components.css:167). An opacity cross-fade on the thumb is an acceptable alternative cue, but a static partial fill is not.

### [medium] The live region the PR was built around never fires: app.js never writes .profile-status, so the kept sentence reaches nobody

`extension/app.html:1130`

**Failure:** The comment and commit justify keeping the paragraph on the grounds that deleting it "would have left a screen-reader user in silence while the panel decided who they were" and that the state is "conveyed by the existing live region". It is not. grep over extension/app.js shows the only references to this state are the two classList lines at app.js:2254 and 2270 — nothing ever sets textContent on .profile-status. The text is present in the initial HTML at parse time, and an aria-live region does not announce content that already exists when it is registered; it announces changes. #profile-stage also carries aria-busy="true" for exactly this window. When checking ends, #welcome-checking gets display:none !important and the region leaves the accessibility tree — removal is not announced either. So no screen reader ever speaks "Checking your account…", before or after this change. What the change actually does is remove the sentence from the sighted channel, where it did work, in exchange for an announcement that does not happen: after this PR nobody gets the status, in any modality.

**Proposed:** Either make the claim true — have setChecking() write the sentence into .profile-status after the element is live, so the region actually fires — or drop the justification and render the sentence visibly (it costs one 19.5px line in a 588px-tall state; measured content is 216.5px of 588px available at 400x700, so there is room).

### [medium] The two tests the PR cites as its constraint no longer verify anything visible, and the docstring now describes behaviour the page does not have

`tests/test_panel_dom.py:3007`

**Failure:** The PR treats these assertions as the reason the strings must stay, but text_of is page.text_content() (test_panel_dom.py:143-144), which returns text regardless of CSS — so lines 3007-3008 now pass against two nodes measured at 1x1 with clip:rect(0,0,0,0). side-panel-startup.test.mjs:384-385 only greps the raw file. Neither can fail on visibility. The docstring at line 2997-2998 — "keeps the product greeting as the stable heading, and shows the status as a separate line" — is now false on both counts: the heading is clipped to 1x1 and there is no status line on screen. A future change that deletes the splash entirely and leaves only the two hidden strings would still be green, and a reader auditing the checking state from this test will believe a visible status line is guarded when nothing guards it.

**Proposed:** Update the docstring to what the state now is, and replace the text_content assertions with ones that pin the real contract: assert the two elements are in the accessibility tree but not visible (page.locator(...).bounding_box() height <= 1, or an aria-snapshot), and assert the new visible content (#welcome-checking .checking-name text, .checking-bar present) so the splash itself is what is guarded.

### [low] "where everything begins" is the only sentence on the panel's first frame, and no guard covers interface copy of this kind

`extension/app.html:1113`

**Failure:** After this change the sole English sentence a user reads while the panel decides who they are is a content-free slogan — measured 140.7px wide at 400px viewport, directly under the product name, with the informative sentence hidden one element below it. The only copy guard in the repo is test_the_interface_stays_english (tests/test_panel_wiring.py:148), which greps for Arabic codepoints and nothing else, so nothing mechanical catches this. It also cuts against the product's documented voice: docs/store-listing.md opens by insisting "Every claim here is checked against what the extension actually declares", and manifest.json:7 describes the product concretely ("A local scraping tool: capture prices from the sites you browse…"). The string is additionally not true of this screen — Profile is the account state, not where anything begins.

**Proposed:** Replace the tagline with the sentence the state actually needs ("Checking your account…", which then also fixes the reduced-motion and live-region findings), or with a factual one-liner drawn from the manifest description. If a tagline is wanted regardless, it is a product decision for the owner, not a side effect of a layout PR — raise it separately.


## ?

### [high] No test asserts the checking state's appearance — the entire splash can be deleted and CI stays green

`tests/test_panel_dom.py:2998`

**Failure:** I deleted `<div class="welcome-mark">` and the whole `<div class="checking-copy">` block (96px mark, "ScrapeX" wordmark, "where everything begins", sweeping bar) from extension/app.html, so the panel's opening frame renders as a completely blank rectangle for the ~1s Chrome takes to answer. Result: `python -m pytest tests/test_panel_dom.py tests/test_panel_startup.py tests/test_signing_in_says_what_happened.py` -> 223 passed; `node --test extension/tests/*.test.mjs` -> 35 passed. Two narrower mutations are also fully green: (a) deleting `animation: sx-checking-sweep 1.4s linear infinite` (app.css:1256) freezes the thumb at the start edge — precisely the "reads as stalled" outcome the PR's own reduced-motion comment at app.css:3082 says is wrong; (b) deleting the whole `.profile-card:has(#welcome-checking:not(.hidden))` rule (app.css:1198-1209) puts the card border, radius, background and shadow back around the splash — the one thing this PR exists to remove. test_the_profile_card_shows_checking_while_chrome_answers is the ONLY test that drives the checking state, and its single visibility assertion (line 3004) is on the `#welcome-checking` wrapper, which keeps a non-zero bounding box via `flex: 1` even when it contains nothing legible. Nothing anywhere in tests/ or extension/tests/ references `.checking-name`, `.checking-tagline`, `.checking-bar`, `.checking-bar-thumb`, `sx-checking-sweep`, or the string "where everything begins". No test sets prefers-reduced-motion at all, so the new reduced-motion branch is also unexecuted.

**Proposed:** Extend test_the_profile_card_shows_checking_while_chrome_answers to assert the presentation it now owns: the wordmark and tagline via `inner_text()` (which respects visibility, unlike the `text_content()` used today), the thumb actually animating via `page.eval_on_selector('#welcome-checking .checking-bar-thumb', 'el => el.getAnimations().length')` > 0, and the card's computed `borderTopWidth`/`boxShadow` being 0/none while checking but NOT while signed-out — that last pair is the only thing that can pin the `:has()` rule.

### [high] The two assertions the PR cites as its reason to keep the strings pass even when the strings are removed from the accessibility tree

`tests/test_panel_dom.py:3007`

**Failure:** The PR's stated rationale (app.html:1112-1124) is that the h1 and status paragraph are kept because a screen reader must still be told, and because two tests read them by exact text. Neither test can observe that contract. `text_of` (tests/test_panel_dom.py:143-144) is `page.text_content(selector)` — Playwright's DOM textContent, which performs no visibility check and returns the string for a `display:none` node. `extension/tests/side-panel-startup.test.mjs:384-385` is `html.includes("Welcome to ScrapeX")` against the raw file, a substring match no styling or attribute can affect. Proof: I edited app.html to put `style="display:none"` on both elements AND removed `role="status" aria-live="polite"` from the paragraph — the checking state then announces absolutely nothing to a screen reader — and `python -m pytest -q tests/test_panel_dom.py -k "profile or welcome or checking"` passed 5/5 while `node --test extension/tests/*.test.mjs` passed 35/35. So the accessibility fallback this PR makes the sole justification for the kept markup is the one property no test in the repo can distinguish from its own absence, and a future edit that silences it ships green.

**Proposed:** Add the one assertion that separates clipped-but-announced from gone. In the checking test, assert the status node is still in the a11y tree — `getComputedStyle(el).display != 'none'`, `visibility != 'hidden'`, and `role`/`aria-live` still `status`/`polite` — and assert the pair that encodes the design intent: `inner_text()` is empty (invisible on screen) while `text_content()` is not (present for assistive tech).

### [medium] The only checking-state test's docstring now states the opposite of what ships

`tests/test_panel_dom.py:2999`

**Failure:** The docstring reads that the card "keeps the product greeting as the stable heading, and shows the status as a separate line." After this PR neither half is true: the greeting is no longer a visible heading (the `<h1>` is `visually-hidden` and the visible wordmark is a non-heading `<span class="checking-name">`, app.html:1108), and the status line is not shown at all. The PR changed the behaviour and left the docstring untouched. This is not a style nit — it is the mechanism by which the gap in Finding 1 stays invisible: the next person auditing coverage finds a test named `..._shows_checking_...` whose docstring asserts that the visible text is the guarded contract, concludes the checking state's presentation is covered, and does not write the test that would actually catch a blank or card-framed splash. That is the most plausible account of how a pure presentation change reached green CI with zero presentation coverage.

**Proposed:** Rewrite the docstring to state what the test now genuinely guards (aria-busy, the checking->signed-in transition, and the two strings being present in the DOM), and say in it that the visible appearance is asserted in <named test> — then create that test per Finding 1, so the docstring stops being a false coverage claim.

### [medium] The hand-synced diagnostic twin has no parity guard — nothing in the repo reads that file

`extension/tests/diagnostic-app-nomodule.html:1086`

**Failure:** The PR duplicates the 11 new markup lines into extension/tests/diagnostic-app-nomodule.html by hand. The repo's own code map calls that file "a byte-level twin of app.html ... will drift if only app.html is edited" (docs/code-maps/2026-08-11-google-removal.md:54), yet grep across tests/, extension/tests/, tools/ and .github/workflows/ finds no test, script or CI step that reads it. The two node tests whose names suggest coverage — "the minimal diagnostic page stays minimal" and "the diagnostic page cannot reach a package" (extension/tests/side-panel-startup.test.mjs:527 and :571) — both read `tests/diagnostic-panel.html`, a different file. Concrete failure: the next change to the checking state edits app.html only (nothing fails to warn), and the no-module diagnostic page — registered at extension/background.js:61 and opened precisely when app.js is broken — keeps rendering the previous checking screen. The tool used to debug the panel then silently disagrees with the product about what the panel looks like, which is the exact failure mode a diagnostic page cannot afford.

**Proposed:** Add a node test next to the existing ones in extension/tests/side-panel-startup.test.mjs that extracts the `#profile-card` subtree (or at minimum `#welcome-checking`) from both extension/app.html and extension/tests/diagnostic-app-nomodule.html and asserts the two are identical after whitespace normalisation. One test converts a documented drift hazard into a failing build.
