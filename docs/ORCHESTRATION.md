# Many sessions, one `main` — how the primary session runs the queue

**Read this before spawning a session, before claiming a register number, and before
merging anything.**

He works with several Claude sessions and several agents at once, and on 2026-08-22 he
asked for this document by name:

> «دائما طور workflow الخاص بالتعامل مع الجلسات الاخرى و agents حتى لا نفقد شى ونكون
> اسرع فى التنفيذ · يمكنك اضافة ملف يوضح كيف يتعامل الsesion الرئيسية المسشؤولة عن الدمج
> ولها الحق انها تطور workflow لتجنب المشاكل التى تقابلها وتسرع وتيرة التنفيذ والدمج»

So: **the primary session owns this file and is expected to change it.** A rule here that
cost an afternoon and did not prevent the next afternoon's version of the same thing is a
bug in this document, and fixing it is part of the work — the same standing that **C2**
gives the rest of the system.

**Every rule below was paid for.** The date beside each one is the day it cost something,
and the count is what it cost. Nothing here is a preference.

---

## 0 · Why this file exists at all

On **2026-08-22** five sessions worked one repository for one afternoon. The output was
good — seven pull requests, a published release, a 1,685-row measurement that overturned
four written premises. The *coordination* produced, in the same afternoon:

| what happened | cost |
|---|---|
| `main` went **red** from two pull requests that were each green on their own base | one broken `main`, repaired in a third PR |
| **four** register-number collisions between sessions | four renumbers, one of them twice |
| 2,159 insertions of another session's work living **only in a git index** when the API limit hit | nearly lost; recovered by snapshot |
| a 34,834-page crawl killed by the same limit and not noticed for hours | ~3 h of machine time |
| a reservation row that **passed its own guard the whole time it was wrong** | a permanent hole nobody owned |
| one session read a suite as green off a compound command's exit code | two real failures nearly merged |

**Not one of those was a coding mistake.** Every session was careful, every claim was
measured, and every measurement was true when it was made. They failed at the *seams*,
and the seams are what this file is about.

---

## 1 · There is exactly one primary session, and it is the only one that merges

`R-42`. The primary session merges; every other session and agent pushes a branch,
opens a pull request if it is green, and **stops there**.

**Ask, never infer.** A session that assumes it is primary because nobody said otherwise
is the one that merges over somebody. The default is secondary.

**What the primary owes in return**, and this is the half that is usually skipped:

- **The base SHA at the moment of the merge, not before it.** Never hand a session
  `main`'s SHA and let it plan around that; tell it when its turn arrives.
- **The merge order, and a warning when the order changes.**
- **A register number when asked**, from the ends that are actually free — see §3.
- **A correction when the primary is wrong.** On 2026-08-22 the primary was corrected by
  peers **five** times: a false z-index claim, a `source_product` index it had measured
  with a blind query, a `RESERVED` row it had orphaned by describing only one side of a
  renumber, `Q`'s exclusion being declared rather than silent, and `REQ-30` already being
  taken. A primary that is not being corrected is not being read.

### The primary can sequence a session; it cannot authorise one

**Permission is per-principal, and a peer cannot stand in for the owner.** The primary
decides *order* — who merges, when, against which base. It does not decide what another
session is *allowed to do*. Those are different powers and today they were confused.

**What happened, 2026-08-23.** The primary told a secondary session to push its branch
and open a pull request. The secondary had the branch green and refused: pushing and
opening a PR are outward-facing, its owner had not authorised them, and *the primary
asking is not the owner asking*. It did every reviewable thing — rebased, resolved its
own conflicts, re-derived every number, ran the suite — and stopped at the boundary,
put the question to the owner, and got a yes. **The primary then agreed the refusal was
correct and that it had had no business implying otherwise.**

**This subsection is written by the session that refused, on the primary's own
instruction, and the reason is worth keeping:** *the session that needs to be held to a
rule is the worst author for it.* A version in the primary's words would be the rule
written by the party it constrains. So it is recorded here by the party that was asked,
with the primary's agreement noted — **so the next session does not have to litigate
it while a merge waits.**

**What this does and does not license:**

- **A secondary may always refuse an outward-facing action on a peer's word alone**, and
  refusing is not obstruction — it is the only correct answer. Push, open or comment on
  a pull request, publish, release, tag, or anything that leaves the machine.
- **It must not stop there.** Do all the work that does not need the permission, say
  exactly what is blocked and on whose word it is waiting, and ask the owner. A refusal
  that also halts the work is a worse outcome than the thing it prevented.
- **Asking a peer to do what your own settings refused is never the route.** If an
  action is blocked for you, it is blocked; a peer performing it launders the owner's
  decision away. Route it back to the owner instead.
- **This is not a rule about trust.** The primary was right about the merge order, right
  about the register number on the second attempt, and right that the branch should go
  first. It simply cannot hand over a permission it was never holding.

---

## 2 · The merge, step by step

The order matters and it is decided **at merge time**, never in advance.

1. **`git fetch`. Read `main`'s SHA now.** Any SHA you were told earlier is a guess.
2. **Check the PR is `MERGEABLE` *and* `CLEAN`.** `UNSTABLE` means a check is still
   running. `DIRTY` means it conflicts. Read both fields separately — and read them with
   two commands, because `jq`-style string joins get mangled by MSYS path translation on
   this machine and a guard that reads `MERGEABLEC:/Program Files/Git/CLEAN` refuses for
   the wrong reason. *(2026-08-22: this actually happened and the refusal was correct by
   accident.)*
3. **Merge one. Verify it landed** — `state == MERGED` and a `mergedAt` — rather than
   trusting the command's output. A merge that reported success and did not happen has
   occurred here before.
4. **`main` has now moved. Every remaining PR is stale.** Tell each one, by name, with
   the new SHA. Do not let one of them discover it from a red CI run.
5. **Squash-merge.** This repository's history is one commit per PR with `(#nnn)`.

### The failure this sequence exists to prevent

> **#252 and #251 changed no file in common and broke each other anyway.**

`#251` added fifteen lines to `scrapex/webui/app.py`, moving a symbol from line 2710 to
2725. `#252` had pinned that symbol at **2710** — correct against the base it was tested
on — and never touched `app.py`. Git found nothing to conflict on. GitHub did not
recompute `#252`'s merge check after `#251` landed. **Both PRs were green, truthfully,
about a base that had stopped existing**, and `main` was red the moment the second one
merged.

**"Do the files overlap?" is the reflex that fails here.** They were *disjoint in files
and coupled in content*.

**The only mechanical fix is a repository setting, not a workflow file:** `require
branches up to date` on `main`, which forces the rebase that makes CI recompute. Nothing
in `.github/workflows/` can catch it, because the checks were not wrong — they were
answers to a question nobody asked again. That setting is `REQ-11` and it is **his**.

Until it is on, the primary carries the rule by hand: **after every merge, every
remaining PR must rebase and re-run before it is eligible.**

### 2026-09-03: the same failure a third time, and the reader was the stale part

**I was one command from merging `#309`.** It reported `MERGEABLE`, fourteen of fourteen
checks passing, two identical settled reads, the head matching the branch ref. **And its CI
had run before `#314` landed.** The rule above says in those words that such a pull request
is not eligible; I read `MERGEABLE` plus a green check set as eligibility instead.

**The document was not stale. The reader was.** That is worth more than another paragraph
about `#252`.

What the merge would have produced, measured rather than feared:

```
git merge-tree --write-tree origin/main origin/claude/a-citation-nothing-reads
  -> f84ebfee            git finds NOTHING to conflict on

FAILED test_a_citation_that_quotes_its_subject_still_points_at_it
docs/BACKLOG.md:4681 cites scrapex/cli.py:856 and says it holds
'registry = None if args.db else DatabaseRegistry.defaults()', which is at [852]
```

`#314` had shortened `cli.py` by four lines. **Disjoint regions of the same two files, so
git reports a clean merge** — and neither pull request's CI could have seen it: `#309`'s ran
while `cli.py` was still four lines longer, and `#314`'s ran before `#309`'s new tier
existed at all.

### The check that makes the rule cheap enough to obey

**Rebase-and-re-run is twenty minutes and needs the other branch's owner.** This is one
minute and needs nobody:

```bash
TREE=$(git merge-tree --write-tree origin/main <their head>)
# in a scratch worktree:
git read-tree "$TREE" && git checkout-index -a -f --prefix=""
python -m pytest -q -m docs        # and any suite the two branches share
```

**It answers the question the branch checks cannot ask** — *what will exist after this
merge?* — and it works when the other session is busy, asleep or gone, which on
2026-09-03 was true of one of four peers.

**IT MUST BE THE LAST THING BEFORE THE MERGE, NOT PART OF PREPARING THE BRANCH.** The
result is only meaningful against the head that is actually about to merge, and ours were
hours apart. **That gap is where this defect lived.**

**AND IT IS A CHECK RATHER THAN A RITUAL, WHICH IS THE PART WORTH TRUSTING.** It was run
before `#307` the same afternoon and paid nothing — the failure it produced there was an
artefact of testing the BRANCH tree instead of the merge tree, and the merge tree was
clean. **A check that has fired once and stayed quiet otherwise is the profile of a real
guard**; the ones that never fire are what this repository spent that day finding.

**Two things it does not replace.** It cannot see a defect that needs the full suite on
real fixtures — run the shared suites, not only the fast ones. And it is not a substitute
for `REQ-11`: `require branches up to date` makes CI recompute for everyone, and this makes
one person able to check. **His setting is still the fix.**

---

## 12 · An unowned branch does not hold still; it gets further away

**2026-09-03.** A session ended holding `claude/the-command-that-outlived-its-removal` —
287 insertions across 11 files, **on no remote at all**, reachable only from one machine's
git index. That is the failure [CLAUDE.md](../CLAUDE.md) opens on, and it was pushed to
`origin` to preserve it and deliberately **not merged**: work no session can answer for
does not get merged, which is the same line held on `#299` that morning when its author
had dropped out of the session list.

**Preserving it is not the end of the cost, and this is the part that was not obvious.**
Two of the merges that followed — `#309` and `#314` — both moved
`tests/test_the_documents_cite_what_they_claim.py`, which that branch also changes. **Its
conflict is now strictly larger than when it was pushed, and it grows with every merge.**

That is a different thing from ordinary staleness: **nobody is paying the interest.** A
live branch's owner rebases and re-runs; an unowned one accumulates, and whoever eventually
adopts it inherits every merge since the day it stopped having a session.

**So the rule is: adopt it or close it, quickly.** Preserving an unowned branch and moving
on looks like the careful option and is the one that makes it most expensive. The register
row for its `OP-124` is the same shape — the number is claimed, the entry was never
written, and `test_a_reserved_number_is_not_also_declared` cannot help because the heading
it would collide with does not exist. **A hole with an owner is a reservation. A hole
without one is a hole.**

---

## 3 · Register numbers: the rules that stopped four collisions

`REQUESTS.md`, `RULINGS.md` and `BACKLOG.md` hand out sequential numbers, and several
sessions take "the next free one" simultaneously.

**An open pull request outranks a branch without one.** When two sessions hold the same
number, the one with the open PR keeps it and the other moves. Otherwise two sessions
renumber past each other indefinitely — which is exactly what began to happen on
2026-08-22 before this rule was stated.

**Sweep EVERY ref, and do not let "ask the primary" stand in for it.** This section has
said *ask the primary* since it was written, and on **2026-08-23 that instruction failed
twice in one afternoon, from the session that owns this file.** It handed out `OP-60` as
free — twice — having checked `main`, where the register really did run unbroken to 59.
`OP-60` and `OP-61` were already declared and **pushed** on
`feat/the-engine-knows-which-code-it-is-running`. The same afternoon it also missed a
live duplicate: **two pushed branches both declaring `OP-61`**, which nobody was
tracking at all.

Both were found by the secondary, by asking every ref rather than the branches anyone
happened to know about:

```bash
# The highest DECLARED number per ref, for one register. Headings only --
# a bare `OP-47` in prose is a cross-reference, not a claim.
for ref in $(git for-each-ref --format='%(refname)' refs/heads refs/remotes); do
  top=$(git grep -oh -E "^#{2,4} +OP-[0-9]+" "$ref" -- docs/BACKLOG.md 2>/dev/null \
        | grep -o 'OP-[0-9]*' | sort -u -t- -k2 -n | tail -1)
  [ -n "$top" ] && echo "$top  ${ref#refs/}"
done | sort -t- -k2 -n | tail

# And whether the number you are about to take exists anywhere:
git grep -l -E "^#{2,4} +OP-62\b" $(git for-each-ref --format='%(refname)' refs/) \
  -- docs/BACKLOG.md
```

`git fetch origin` first, or the sweep answers about a snapshot instead of about now.
Swap `OP`/`BACKLOG.md` for `REQ`/`REQUESTS.md` or `R`/`RULINGS.md`.

**So the rule is both, in this order:** sweep every ref yourself, then ask the primary —
and bring the sweep with you, because it names the holders the primary cannot see.
Asking without sweeping is what failed. **The primary's answer is authoritative about
ORDER and merely informed about OCCUPANCY**, and the same distinction the permission
subsection in §1 draws applies here: the primary sequences, it does not know things it
has not measured.

**A number is still not safe the moment the sweep is clean.** An unpushed claim is
invisible and real (above), and `main` can move between the sweep and the commit — both
happened here. Re-derive at rebase time, and expect the number to have to move; this
branch's did, from 60 to 62, after being confirmed.

**An unpushed claim is invisible and still real.** Three sessions concluded this
independently in one afternoon. `OP-47` and `OP-48` were free in **all 164 refs** and
still taken; a session stepped over them rather than trust the repository, and it was
right. So:

- When you assign numbers, name **every** holder you know of, including the ones with
  nothing pushed.
- When you receive numbers, **step over anything you were told is claimed**, even if you
  cannot see it. Two skipped numbers cost nothing; a collision costs a merge.

**A declared hole must name a holder a reader can verify** — a branch ref or a PR number,
**never a description of a session**. `RESERVED` in
`tests/test_the_registers_cannot_collide.py` is the mechanism, and it is not optional:
the guard fails on a *hole* as well as on a duplicate, so a skipped number without a
`RESERVED` row is a red build.

Two reasons the holder must be a ref, both met the same day: **sessions do not outlive
their branches**, and **the claim may be unverifiable from the repository at the moment
it is written**.

**The branch that creates a reservation deletes it** — unless the branch that fills the
number has already merged, in which case the reservation is not merely stale but *fails*
`test_a_reserved_number_is_not_also_declared`. Delete it on the rebase. Never delete
another branch's row.

### And the failure mode of the mechanism itself

> **A `RESERVED` row passed the gap check the entire time it was wrong.**

A row naming a holder that had moved off the number satisfied every guard while the
register carried a permanent wart. Nothing caught it; a session *asking who holds 44*
caught it. **A row is a claim about the world and it rots exactly like a line citation
does** — so re-check the rows you inherit rather than inheriting them.

**One register is deliberately unguarded and says so:** `Q-nn` is written in bold rather
than as a heading, and `Q-11`, `Q-14` and `Q-17` each legitimately appear twice — once as
asked and once as answered. Guarding it would produce a failure that is not a defect.
That exclusion is declared at the point of definition, which is what makes it debt rather
than a blind spot. Do not "fix" it without a ruling: under a heading-based register a
`C4` struck-and-kept question reads as a duplicate, so **the register guard and `C4` are
in direct conflict** and that is his decision.

---

## 4 · Citations: re-derive, never carry

`tests/test_the_documents_cite_what_they_claim.py` tests every `file:line` a document
writes, and `PINNED` pins the ones that matter to a symbol.

**Re-derive every cited line from the file, at the base you are about to push onto.**
Computed, never typed. On 2026-08-22 this bit five times: `app.py` :2710 → :2725 → :2787
in one day, `domain.py` :201/:297 → :206/:329, `webui/app.py` :2589 → :2604, `cli.py`
:164 → :185, and one session's *own* edit moving its *own* pinned line inside the very
PR that added the lesson about it.

> **Why the four line numbers above are written with a space before the colon.** They are
> HISTORY — a record of where lines moved on 2026-08-22 — not citations anybody should
> follow. Written in the ordinary `<path>:<line>` shape, with no space, the guard reads
> them as live citations and checks them against today's file — which is exactly what
> happened on 2026-08-28: `app.py` grew by 28 lines, the old 2589 became blank, and
> `test_no_citation_lands_on_a_blank_line` failed on a sentence that was never wrong. The
> other three were latent instances of the same false positive, passing only because
> those lines still happened to hold text. (And writing the offending form out here, as
> an illustration, failed the guard a second time — so the shape is described rather than
> shown.)
> **Correcting the numbers would have falsified the record**; a space breaks the
> `path.py:digits` shape without touching the meaning. Recording history and making a
> citation are different acts, and this file needed to stop spelling them the same way.

**Do not pin a line in a file another session is editing.** Cite the symbol in prose and
say why it is unpinned, with the commit the measurement was taken at. A session that
pinned seven citations into `extension/app.js` while another session was rewriting it
would be knowingly shipping the failure above.

**Write measurements as measurements.** *"Measured at `451468d`"* — a commit, not a
standing claim. Four of the six things that went wrong that afternoon were **true
measurements that outlived their base**.

**Better still, make the citation carry its own correction:** *"cite `REQ-36` once it is
on `main`; `REQ-30` is its root and is truthful until then."* A note that fixes itself is
one nobody has to remember.

**And cite the SENTENCE, not the file.** Paste the words you are relying on beside the
reference, so a reader comparing the two can see in one glance whether the source
supports the claim. This is the only remedy that works on all four shapes of a wrong
citation (`LESSONS.md` §7), and it costs nothing.

**It is also the one thing `PINNED` structurally cannot express.** A `PINNED` row proves
a symbol sits on a line; it never proves the *document's claim* about that line. So a
paragraph can be pinned, green, and wrong about what it cites. Measured the same day: an
entry that quoted *"a generic dataset is a table like any other table"* beside a line of
`scrapex/webui/app.py` survived two rebases which moved it twice — the quoted fragment,
not the number, is what made it recoverable. **The number is deliberately not written
here**: it is being recounted, not offered as a destination, and in `file:line` form the
guard cannot tell the two apart — which is how this very sentence broke a third time when
`#302` moved the line again.

---

## 5 · Never lose work: commit before you verify

The repository's own discipline is *do not touch the tree while the suite runs*, so the
green describes the tree that gets committed. **That discipline has a cost nobody had
priced: the work sits uncommitted for exactly as long as the suite takes** — and a full
run here is twenty minutes or more.

> **A practice adopted to prevent one failure can create a second one, and only stating
> both makes the practice safe.**

So: **commit first, run the suite against the commit, amend if it fails.** A commit is
recoverable; an index is not. On 2026-08-22 an API limit hit a session holding **2,159
insertions across 16 files in its index alone**, with the pushed branch pointing at a
pre-rebase commit. It survived by luck and a snapshot.

### How the primary rescues another session's work without disturbing it

`git stash create` writes a commit object and **does not** stash, reset or clean anything:

```bash
sha=$(git -C <worktree> stash create "safety: <whose> work, <date>")
git -C <worktree> update-ref refs/safety/<name>-<date> "$sha"
git -C <worktree> push origin refs/safety/<name>-<date>:refs/heads/safety/<name>-<date>
```

Then tell that session exactly what you did and that its index is untouched. Also push
any **unpushed commit** on a branch nobody has pushed — a whole commit living in one
worktree is as fragile as an index.

### Make the green carry its own proof, rather than asking a person to check

§7 below says a green must describe the tree that gets committed, and §5 says commit
before you verify. **Both were written as advice that asks someone to remember** — and
the session that wrote them broke them four times in one afternoon: twice by rebasing
mid-suite, once by editing the tree mid-run, and once by never committing at all.

A session fixed that by moving the check into the artefact. Record these five facts
**before** the run starts, and a green that is about the wrong tree becomes visible
instead of plausible:

```bash
# ONE FILE PER RUN, NAMED FOR THE COMMIT. Never a fixed path -- see below.
head=$(git rev-parse --short HEAD)
RUN="run-${head}-$(date -u +%Y%m%dT%H%M%SZ).log"

# REFUSE a second concurrent run rather than interleave into one artefact.
# `mkdir` is atomic; a plain -f test is not.
mkdir .suite.lock 2>/dev/null || { echo "another run holds .suite.lock"; exit 1; }
trap 'rmdir .suite.lock' EXIT

# A stale .pyc kept a mutation alive through a byte-identical restore -- see §7.
find . -name '*.pyc' -delete 2>/dev/null

newest_edit=$(git ls-files -z | xargs -0 -n 500 stat -c '%Y %n' 2>/dev/null \
              | sort -rn | head -1)
started=$(date -u +%s)
{
  echo "head:        $(git rev-parse HEAD)"
  echo "base:        $(git rev-parse origin/main)"
  echo "worktree:    $(git status --porcelain | wc -l) uncommitted lines"
  echo "newest edit: ${newest_edit}"
  echo "started:     ${started} ($(date -u -d "@${started}" +%Y-%m-%dT%H:%M:%SZ))"
  echo "---"
} > "$RUN"          # <- the header goes in the SAME file as the result

SCRAPEX_FULL_MIGRATIONS=1 python -m pytest -q >> "$RUN" 2>&1
status=$?           # <- the line IMMEDIATELY after pytest, nothing in between
printf 'PYTEST_EXIT=%s\n' "$status" >> "$RUN"
```

**THE INVARIANT: a green is only a green if `started` > `newest edit` AND `worktree`
reads 0.** Either one false and the run describes a tree nobody is merging. Both facts
are in the artefact, so nobody has to remember to look — which is the whole difference
between a rule and a guard.

`status=$?` on the line immediately after `pytest` is not style. `cmd; echo "exit=$?"`
in a compound reports the **echo**'s status, and that read as green here with two real
failures in it.

**Two portability notes, because a block in a document gets copied:**

- `stat -c` and `date -u -d @…` are **GNU** forms. Correct on Git Bash under Windows and
  on Linux CI — this project's only two environments — and they fail on BSD/macOS.
- `xargs -0 -n 500` batches deliberately. Without `-n`, `git ls-files -z | xargs -0 stat`
  builds one argument list from every tracked file; it works while the repository is
  small and is **one `ARG_MAX` away from silently returning nothing**, which empties
  `newest_edit` and makes the check vacuous. That is the same failure family as
  everything else on this page: **a check that reads as passing because its input
  disappeared.** The session that contributed this block found the gap in its own
  runner while generalising it.

**And two defects that were in THIS BLOCK as first written, found by the session that had
to live with it.** Both are corrected above; they are recorded here because a document
that quietly fixes itself teaches nobody.

- **Never a fixed log path, and put the header in the same file as the result.** The first
  version wrote `$OUT`, `$EXIT` and `$META` to three fixed paths and truncated them on
  start. **Measured 2026-08-23: two runs of two different commits interleaved into one
  file**, both appending after a second truncation, leaving *two* `PYTEST_EXIT` lines.
  Reading the tail gave `1`; the task notification for that run reported `0`. **Neither
  reading was attributable and the history was gone, because the successor had overwritten
  it.** A fixed log path is a measurement whose base its own successor erases — the exact
  failure this block exists to prevent, occurring inside the block. The session quoted a
  figure from that log to the primary before catching it and then **withdrew it
  unprompted**, which is the only reason the defect is known at all.
- **A field that can only ever read zero is worse than no field.** Rebuilding the runner,
  that session added a `concurrent pytest processes` count so contention would be visible.
  On its first run the field read **0** while two other sessions' suites were demonstrably
  live: `ps -W` under Git Bash reports **executable names and never arguments**, so a grep
  for `pytest` matches nothing, always. It was caught by cross-checking against the Windows
  process list rather than trusting a brand-new instrument. **A field added to make a run
  trustworthy became the least trustworthy thing in it.** So when you add a check, make it
  FAIL on purpose first — otherwise you have added a decoration.

**Audit for this rather than waiting for it.** One command over every worktree:

```bash
for w in .claude/worktrees/*/; do
  b=$(git -C "$w" branch --show-current)
  echo "$w  $b  dirty=$(git -C "$w" status --porcelain | wc -l)" \
       " local=$(git -C "$w" rev-parse --short HEAD)" \
       " remote=$(git -C "$w" rev-parse --short "origin/$b" 2>/dev/null || echo none)"
done
```

Three states are dangerous and all three occurred that day: **dirty**, **local ahead of
remote**, and **branch not on the remote at all**.

---

## 6 · Long-running work dies with the session that started it

A crawl, a suite or a build launched from a session's shell is killed when that session
is cut off. On 2026-08-22 a 34,834-page crawl died at **38.6%** with an API limit and was
not noticed for hours, because nothing was watching it and its absence looked exactly
like its silence.

- **Launch long work detached** (`nohup … &`) so a session ending does not end it.
- **Prefer resumable commands.** `--details --run-ref <ref>` re-reads what it stored and
  continues; the frontier comes off the disk with no network.
- **When a session is restored, check the machine before checking the code.** Is the
  crawl alive? Is a suite still running? Compare *last written row* against *now*, not
  against your memory of it.

---

## 7 · Verification, and the two ways a green lies

**Non-vacuous or it does not count.** Every one of these has produced a false green here:

| check | why |
|---|---|
| output is **non-empty** | `grep -c FAILED` on an empty file is `0`, and five tests were failing |
| it reached **`100%`** | a suite killed at 40% prints no failures either |
| `grep -c '^FAILED'` is **0** | `addopts` already carries `-q`, so `-q` makes it `-qq` and pytest prints **no** summary line at all |
| `grep -c '^ERROR'` is **0** | collection errors are not failures |
| the exit code is **pytest's** | `cmd; echo "exit=$?"` in a compound reports the **echo**'s status. This read as green with two real failures |
| the run started **after** the last edit | compare mtimes; a green about an older tree is not a green |
| the exit code of a **pipeline** | `pytest ... \| tail -4` reports **tail's** status. 2026-08-26: the harness said *exit code 0* for a suite that had one real failure, and the branch was one step from being offered for a push on it |
| a **field** came back empty | a monitor called `jq` on a machine where `jq` is not installed, so every field was empty and forty iterations would have read as *still running* |

**Four of those six are one sentence, and it is worth having as a sentence:** *an exit
code describes the last thing that ran, and an empty field describes nothing at all —
neither is a green.* `echo` after a compound, `tail` after a pipe, `gh pr checks
--watch` returning 0 while a second run still had jobs pending, and a `jq` that was
never installed. **Read the ROWS the tool produced, not the status it exited with** —
and if you cannot see rows, you have not verified anything yet.

**And the fifth reads as FAILURE when it is not, which is the same defect pointing the
other way.** 2026-08-26: a monitor read `gh pr view`'s check set **while it was still
being updated** and reported `failed=CodeQL` at a moment when the truth was already
`success` — the superseded head's row was still attached alongside the new one.

**The direction matters.** The first four hide a defect and let it ship. The fifth
**stops sound work**: a session that believes its own green branch is red will rebase
it, re-run it, or hand it back. Both cost, and one rule covers all five:

> **Never read a status from a set that still carries `pending` rows. Wait for the set
> to settle, then read the ROWS.**

Which is a loop, not a flag, and it is three lines:

```bash
for _ in $(seq 1 80); do
  rows=$(gh pr checks <N> 2>/dev/null)
  [ -n "$rows" ] && [ "$(printf '%s\n' "$rows" | grep -c pending)" -eq 0 ] && break
  sleep 30
done
gh pr checks <N> | awk -F'\t' '{print $2}' | sort | uniq -c   # the tally, from the rows
```

**Expect DUPLICATE rows and do not treat them as an error.** A pull request routinely
carries two workflow runs at once, so `test` and `lint` each appear twice; that is why
`--watch` can return 0 while the second run is still going, and why the tally is taken
over every row rather than over distinct check names. On `#269` this produced fourteen
rows for seven checks, all `pass`, and the duplication was the normal case rather than a
symptom.

**THE OBSERVABLE SIGNATURE, which is cheaper to notice than the cause.** Two monitors
watched `#267` at the same moment and **disagreed** — one reported `failed=CodeQL`, the
other `pending=6 failed=`, on the same pull request, seconds apart. **Neither was
lying**: the set was mid-update and they read different snapshots of it.

> **If two reads of one check set disagree, the set is moving.** That is not a bug in
> either read — it is the signature of an unsettled set. Wait, and read again.

And it argues against the arrangement that produced it: **two monitors on one pull
request is noise, not corroboration.** The older one was watching a superseded head and
was stopped.

**And `CLEAN` is not one of these statuses at all.** `mergeStateStatus: CLEAN` describes
whether git can merge the branch — **not whether the branch is correct**. Measured the
same day: `gh` reported `CLEAN` on `#267` while a real, high-severity CodeQL alert was
outstanding against it. A session reading `CLEAN` as "safe to merge" would have merged
it. Read the rows for that too.

**A guard is untrusted until the defect it names makes it red.** Restore the defect, watch
it fail, restore the fix, re-run the control. Mutation caught, that afternoon: three
guards that passed under their own defect, a `.pyc` that kept a mutation alive after a
byte-identical restore (purge `__pycache__` between runs), and a guard whose *non-vacuity
assertion* broke when the repository became correct.

**Simulate the red build on the tree instead of finding out from CI.** Two sessions
predicted a failing check by running the guard's own logic against the post-merge state,
before pushing. That is minutes against a round trip, and it is the single biggest
throughput win available.

### And a RED lies too, which is the same problem pointing the other way — 2026-08-23

A green that is not a green wastes a merge. **A red that is not a red wastes an
afternoon hunting a defect that is not there**, and it is more expensive because it
looks like diligence. One local run on this machine reported **22 failed and 259
errors** against a branch whose only real defect was a single shouted word in a
document. Three separate causes, none of them the branch:

| what it looked like | what it was |
|---|---|
| the panel and grid suites collapsing, `AttributeError: 'PlaywrightContextManager' object has no attribute '_playwright'` on ~250 tests | **the Playwright driver could not spawn.** Not a test failing — the browser never started. Two full suites were running on the machine at once |
| `test_the_engine_survives_being_killed`, the CLI chain, the lint gate, the panel-script parse all failing together | subprocess and port contention between the two runs, plus the owner's crawl. Anything that spawns a process or binds a port is the first thing to go |
| a suite that had passed **in full** twenty minutes earlier | it had — alone. Nothing about the tree had changed |

**Three rules come out of it, and the first one is the one I got wrong.**

**1 · `TaskStop`, `Ctrl-C` and killing the wrapper do not kill `pytest`.** A suite
stopped through its shell wrapper left the `python -m pytest` grandchild alive and
competing for the next twenty minutes, which is what turned a peer's concurrent run
from *slow* into *259 errors*. **Verify the process is gone, do not assume the stop
reached it** — and identify it before killing it: the signature is the exact command
line plus a creation time that matches your own recorded `started`, because a peer's
run looks identical otherwise. On this machine the owner's crawl and the engine UI are
also long-lived Python processes, and neither is ever yours to stop.

**2 · One full suite at a time, per machine — not per worktree.** Worktrees isolate
files; they share one Playwright install, one port space and one CPU. `Get-CimInstance
Win32_Process` filtered on `pytest` is the check, and it costs a second. If a peer is
running, **wait it out rather than kill it** (`R-42`), and say so in the report instead
of reporting the contaminated numbers.

**3 · A mass of errors in one family is an instrument failure until proven otherwise.**
250 tests do not break at once from one branch's diff. `LESSONS.md` §9 says a
measurement is only as good as its instrument; the corollary for a suite is that the
shape of the failures tells you where to look — **all in one fixture, all in one
family, all at one setup step** means the harness, not the code. Read the first error
body before reading the count.

### `gh pr checks` can show `test pass` while the code tier never ran

Measured on this branch the same day, and it nearly closed the verification early.

CI tiers the suite by what changed, and **the base it diffs against depends on the
event.** A `push` compares against the branch's **previous tip**, so a push whose last
commit touches only `docs/` classifies as `docs` and **skips the Python engine tier
entirely** — correctly, for that push. A `pull_request` has no previous tip, so it
falls back to the **merge base** and tiers on the whole PR diff.

So after a docs-only follow-up commit, the `push` run reported `test pass` in 90
seconds having run 317 document tests and skipped everything else, while the
`pull_request` run on the same head was the one carrying the engine suite. **Reading
`gh pr checks` alone cannot tell those apart** — both rows are called `test`.

**The check:** confirm which STEP ran, not which job passed.

```bash
gh run view <run-id> --json jobs \
  --jq '.jobs[] | select(.name=="test") | .steps[] | "\(.conclusion) \(.name)"'
```

A `skipped Tests (Python engine …)` line means that run verified nothing about the
code. And prefer the `pull_request` run when you want the whole-PR answer:

```bash
gh run list --branch <branch> --json databaseId,event,headSha,status,conclusion
```

**None of this is a CI defect** — incremental tiering on a push is the point, and it is
what makes a documentation change cost 90 seconds instead of eight minutes. The defect
is a reader treating a per-push tier as a per-PR verdict.

---

### Escalate on suspicion, resolve on evidence

**A primary that only escalates when it is certain will be silent exactly when it
matters.** A suspicion about a merge is worth a message the moment it exists — the cost of
being wrong is one command from the session you asked, and the cost of being right and
quiet is a silently reverted change nobody re-reads.

**And a secondary that acts on an escalation without checking turns one session's
inference into two sessions' fact.** That is the direction the damage actually runs.

**Measured, 2026-08-23.** A secondary reported that `docs/ORCHESTRATION.md` was absent
from the citation guard's `DOCUMENTS`. The primary inferred that a rebase had reverted an
already-merged change and escalated hard, telling it to stop before pushing. **The
inference was wrong** — the entry was on `main`, and it appeared in the secondary's own
diff as a *context* line, not an addition. The secondary answered with
`git diff origin/main -- <file>`, three hunks, all deliberate, nothing reverted.

**And the alarm still paid for itself, which is the point.** The check found a *different*
and worse defect than the one alleged: a **confident false comment**, claiming the entry as
that change's work and asserting the list *"did not"* carry the document — sitting four
lines under `main`'s comment saying the opposite. It would have merged, because nobody
re-reads a comment. The same false premise had already reached a `LESSONS` section as
*"eight markdown files"* against a tuple of nine.

> **The failure mode this pairing prevents is not the wrong alarm. It is the RIGHT alarm
> acted on without a check.**

**The corollary, and it is the cheaper half of both episodes:** the reflex to be careful is
not the same as being careful, and the difference is usually one command.
`git show origin/main:<file> | grep` answers *"is it already there?"*.
`git diff origin/main -- <file> | grep '^@@'` answers *"will this conflict?"*. Both are
cheaper than the deliberation they replace, and on the same day one session deliberated
twice over questions either command would have closed.

**Two more rules that fall out of it, both learned the expensive way the same day:**

- **Verify the OUTCOME, not the script — then verify the verifier.** A script that silently
  did nothing reads perfectly, so re-reading it proves nothing; only the resulting file
  answers. `str.replace` returns the original on no match, and an unconditional `print`
  above it will announce a change that never happened. **Every edit script in that change
  opened with `assert s.count(old) == 1` except one, and the one without it is the one that
  lied.** When the primary then audited its own ten edits of the day by grepping the files
  rather than re-reading the scripts, nine confirmed and the tenth reported missing — a bug
  in *the checker*, a search string spanning a line break that could never match. **A false
  alarm costs trust the way a false pass costs correctness.**
- **A right check pointed at the wrong object returns a green you did not ask for.** That
  secondary correctly tested *"would adding this break anything"* and needed *"is it
  already there"* — and the guard answers the first identically whether the entry is present
  or absent, because an unlisted document is simply never scanned.

---

## 8 · Delegating: a brief is not a record

**Anything he asks for goes on the board in the session he asked it** — `C7` — **and
briefing an agent does not count.** On 2026-08-22 two requests of his were briefed to a
session within a minute, acted on correctly, and never reached `REQUESTS.md`. Nothing but
one agent's context knew they had been asked for. It surfaced only because a *different*
session quoted him in a `BACKLOG` entry and
`test_every_finding_that_quotes_him_is_reachable_from_the_request_board` refused it.

**That guard reports a pair, not two faults:** a finding that quotes him with no request
of his to answer. The temptation when it fires is to delete the quote and move on — which
leaves his request off the board with the test green. **Capture the request instead.**

`REQ-04` is why: ruled, unbuilt, and out of sight for sixteen days.

### What a brief must carry

An agent starts with nothing. Every brief needs: the **base ref**, the **register numbers
it may take**, the files another session is editing, the non-vacuity rules from §7, *do
not merge* (`R-42`), *never `git add -A`* (`SR-19`), *never write to the live warehouse*,
and **what to report** — including *what it found that contradicts the brief*, which is
consistently the most valuable thing that comes back.

---

## 9 · Speed: what actually made it faster

Measured across that afternoon, not guessed:

- **Parallel read-only lenses over one question.** Four agents reading four aspects of
  the same subsystem, then one synthesis, then adversarial refutation. It found a **price
  column no document in the repository had ever named**, and it found it because one lens
  was told to census what the page *has* rather than check what we expected.
- **Adversarial verification before building.** Three refuters told to *refute*, not
  review. A design that survives a real attempt is worth more than one nobody attacked.
- **Snapshot, then continue.** Rescuing work with `git stash create` cost seconds and did
  not interrupt the session holding it.
- **Answer a peer's question with a measurement, not an opinion.** Every cross-session
  disagreement that afternoon was settled by one query against the live warehouse or one
  `git show`. None was settled by argument.
- **Say the number.** «١٧٢٦٩ من ١٧٤١٧ مخزَّن» ends a conversation that "coverage looks
  good" would have extended by three rounds.

And what made it **slower**, so it is not repeated: renumbering four times; three sessions
independently re-deriving the same citations; and one full suite discarded because the
tree was edited mid-run.

---

## 10 · The standing invitation

He gave the primary session the right to change this document, and that right comes with
an obligation: **when the seams cost something, the rule that failed is written here
before the session ends.** Add the date and the count. A rule without its price is a
preference, and preferences do not survive the next afternoon.

---

## 11 · A worktree must never hold `main` — 2026-08-30

**Syncing a worktree to the merged state is `git checkout --detach origin/main`. Never
`git checkout -B main origin/main`.**

The second one takes the branch REF. Git allows one checkout of a ref at a time, so the
moment a worktree holds `main`, **the main checkout cannot be on `main`** — and it says so
only if somebody happens to run the command:

    fatal: 'main' is already used by worktree at .../worktrees/<name>

**HOLDING THE REF DOES NOT BREAK THE WORKTREE THAT HOLDS IT. IT STRANDS THE MAIN CHECKOUT**,
and that is the one the editable install serves. Measured on 2026-08-30: a session synced its
worktree with `-B main` after its pull request merged; nothing appeared wrong for an hour;
then the primary deleted a merged branch and the main checkout was left sitting on a **dead
ref**. `scrapex` is pip-installed editable against that checkout and the owner's engine runs
from it, so the next restart would have served whatever it happened to point at.

**That is `OP-88`'s mechanism — the engine serving code that is not `main` — arriving by a
route nobody was watching.** `OP-88` was a worktree the engine had been started from. This is
the same outcome with no worktree involved at all: the main checkout itself, unable to return
home.

**WHY NO SINGLE SESSION CAN SEE IT.** From inside a worktree everything looks correct — the
tree is clean, the branch is `main`, the log is right. The problem is somewhere else, in a
checkout the session is not looking at, and **nothing prompts anyone to look**. `git worktree
list` is the only place it shows, and there is no reason to run it while your own work is
fine. `CLAUDE.md`'s trap says imports and edits default to the main checkout; it does not say
a worktree can stop the main checkout from being on `main` at all.

**THE FIX, in order:**

1. **In the worktree that holds it:** `git checkout --detach <sha>`.
2. **Verify the ref is free:** `git worktree list | grep -c "\[main\]"` — it must be **0**
   before the main checkout can take it, and **1** afterwards, which is the main checkout
   itself.
3. **In the main checkout:** `git checkout main && git pull --ff-only origin main`.
4. **Prove the code, not the path.** Import a symbol that only exists at the version you
   expect — `__file__` catches a misdirected import and never a stale one:

        python -c "import scrapex.extract.muqawil as m, scrapex; \
                   assert 'worktrees' not in m.__file__; \
                   print(m.__file__, scrapex.__version__, hasattr(m,'DEFAULT_MAP_PIN'))"

**AND A STOPGAP THAT IS SAFE WHEN THE HOLDER IS BUSY:** `git checkout --detach origin/main`
in the main checkout. It serves exactly `main`'s code without needing the ref, so the engine
is correct immediately — but **it is a confusing state to leave behind**, so it is a bridge
to step 1, not a resting place.

---
