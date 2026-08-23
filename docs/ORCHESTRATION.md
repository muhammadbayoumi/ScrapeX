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

---

## 3 · Register numbers: the rules that stopped four collisions

`REQUESTS.md`, `RULINGS.md` and `BACKLOG.md` hand out sequential numbers, and several
sessions take "the next free one" simultaneously.

**An open pull request outranks a branch without one.** When two sessions hold the same
number, the one with the open PR keeps it and the other moves. Otherwise two sessions
renumber past each other indefinitely — which is exactly what began to happen on
2026-08-22 before this rule was stated.

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
Computed, never typed. On 2026-08-22 this bit five times: `app.py:2710 → 2725 → 2787` in
one day, `domain.py:201/:297 → :206/:329`, `webui/app.py:2589 → :2604`, `cli.py:164 →
:185`, and one session's *own* edit moving its *own* pinned line inside the very PR that
added the lesson about it.

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
entry that quoted *"a generic dataset is a table like any other table"* beside
`scrapex/webui/app.py:1048` survived two rebases which moved that line twice — the quoted
fragment, not the number, is what made it recoverable.

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
OUT=<run log>  EXIT=<exit status>  META=<provenance>
rm -f "$OUT" "$EXIT" "$META"

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
} > "$META"

SCRAPEX_FULL_MIGRATIONS=1 python -m pytest -q > "$OUT" 2>&1
status=$?          # <- the line IMMEDIATELY after pytest, nothing in between
printf '%s\n' "$status" > "$EXIT"
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

**A guard is untrusted until the defect it names makes it red.** Restore the defect, watch
it fail, restore the fix, re-run the control. Mutation caught, that afternoon: three
guards that passed under their own defect, a `.pyc` that kept a mutation alive after a
byte-identical restore (purge `__pycache__` between runs), and a guard whose *non-vacuity
assertion* broke when the repository became correct.

**Simulate the red build on the tree instead of finding out from CI.** Two sessions
predicted a failing check by running the guard's own logic against the post-merge state,
before pushing. That is minutes against a round trip, and it is the single biggest
throughput win available.

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
