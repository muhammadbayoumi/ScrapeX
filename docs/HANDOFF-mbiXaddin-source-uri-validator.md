# Handoff — mbiXaddin decides "is this Google Sheets" by searching the whole string

> **Resolved 2026-08-13.** mbiXaddin PR #26 replaced the substring with an
> absolute-URI host parse, exact `docs.google.com` / `spreadsheets.google.com`
> matching, trailing-root-dot normalisation, and an `ERR_FORMAT` finding for
> impostor addresses. The security consequence below was refuted: the rule is
> advisory and SOURCE_URI is owner-authored. ScrapeX re-read that behaviour and
> updated its contract mirror on the `the-addin-parses-its-host` branch. The
> remainder is kept as the historical handoff and mutation checklist.

*Paste everything below into a session working in
`C:\Users\User01\source\repos\mbiXaddin`. It is self-contained; that session
needs no knowledge of the conversation this came from.*

---

## Before anything: your first job is to REFUTE this

A finding arrived from another repository. It was found by CodeQL pointed at a
*copy* of your rule, not at your rule, and the person reporting it has not run
your code. **Treat it as a claim, not as a work order.**

Do not open an editor until you have answered, from the code in front of you:

1. Does `SourceUriValidator` really decide by substring, or is there a host check
   somewhere else — earlier in the pipeline, in a policy class, in a config
   allow-list — that makes this unreachable?
2. Is the address that reaches the HTTP client the same string that was
   validated, or is it rewritten in between?
3. Does anything authenticate the fetch, refuse redirects to another host, or
   check the content type before parsing?
4. Can a value that fails these checks actually be *stored* in the workbook by
   somebody who is not already the owner? **Who is the attacker here, and what
   access do they need?**

Question 4 is the one that decides whether this is worth fixing at all, and it
is the one most likely to shrink the finding. Say plainly what you conclude.

**If you cannot reproduce it, say so and stop.** A refutation with file:line is a
better outcome than a repair of something that was never broken. The reporting
session has been wrong twice recently in exactly this way — it read a rule
correctly and then *assumed a consequence* — so it will not be surprised.

---

## The claim

`mbiXaddin/Core/Validation/SourceUriValidator.cs:79-80`:

```csharp
bool isGoogleSheets = sourceUri.IndexOf("docs.google.com",
    StringComparison.OrdinalIgnoreCase) >= 0;
```

The host is never parsed. The substring may appear anywhere — in the query
string, in the path, in a subdomain of somebody else's domain. So both of these
are "a Google Sheet" as far as this validator is concerned:

```
https://attacker.example/collect?x=docs.google.com&output=tsv
https://docs.google.com.attacker.example/pub?gid=1&output=tsv
```

Each satisfies **every** check the file makes: it starts with `https://`
(`:44-49`), its authority contains a dot (`:66-75`), it contains `output=tsv`
(`:83-85`) and it contains `gid=` (`:87-88`). Validation passes clean.

### Why that matters more than a validator usually does

The claim is that what happens next has no second line of defence. Verify each
of these yourself — they are the whole argument:

| | claimed location |
|---|---|
| the only runtime check is `StartsWith("http")` | `Infrastructure/Services/Ingestion/DataIngestionService.cs:734` |
| plain GET, **no Authorization header, no cookies, no OAuth** | `Infrastructure/Network/HttpClientService.cs:393-465`; the comment saying so is at `Core/Entities/DataSourceEntity.cs:666-668` |
| follows up to **5 redirects**, including cross-host | `Infrastructure/Network/HappyEyeballsHandler.cs:97-108,442` |
| **Content-Type is never inspected** | `Infrastructure/Services/Sync/Metadata/TsvParser.cs:48-52` |
| the bytes are then parsed as the table's rows | `Infrastructure/Services/Ingestion/StreamingTsvReader.cs:62-72,101-108` |

The markup sniff at `SourceIntegrityGate.cs:64-69` rejects a payload starting
with `<!DOCTYPE`, `<HTML` or `<?XML` — **note that it does not help here**, since
a TSV response is not markup. Confirm that reading.

If all of the above holds, the consequence is: an address in the `SOURCE_URI`
column can point anywhere, and whatever it returns becomes rows in the owner's
Excel table, unauthenticated.

---

## If it holds — the repair

Parse the host and compare it. Keep everything else exactly as it is: the TSV
error, the gid warning, the wording, the error codes, the order they are
yielded in.

```csharp
// Sketch, not a patch — write it to fit the file.
bool isGoogleSheets = false;
if (Uri.TryCreate(sourceUri, UriKind.Absolute, out var parsed))
{
    var host = parsed.Host;                      // already lower-cased by Uri
    isGoogleSheets = host.Equals("docs.google.com", StringComparison.OrdinalIgnoreCase)
                  || host.EndsWith(".google.com", StringComparison.OrdinalIgnoreCase);
}
```

Three things to decide deliberately rather than by accident, and to **write down
in the commit message**:

1. **`.google.com` or only `docs.google.com`?** Broader accepts
   `spreadsheets.google.com`, which the current substring rule *rejects* — so
   this is a behaviour change in the permissive direction, not only the strict
   one. Say which you chose and why.
2. **What happens to an address that mentions Google but is not served by it?**
   Silently dropping to "not a Google Sheet" means it skips the TSV and gid
   checks and is fetched anyway. A new `ValidationResult.Fail` naming the real
   host is the more useful answer. Its code should be
   `SystemConstants.ErrorCodes.InvalidFormat` (`ERR_FORMAT`) — the same code
   every other rule in this file uses (`SystemConstants.cs:356`).
3. **Local paths.** The `isLocal` branch at `:44-49` never had a host. Make sure
   the change does not alter it.

### Tests

`tests/Core.Tests/SourceUriValidatorTests.cs` already exists and already uses the
real published shape at `:64,74`. Add cases there — at minimum the two attack
addresses above, plus `https://spreadsheets.google.com/pub?gid=1&output=tsv` for
whichever decision you took on point 1.

**Then break your own fix and confirm the tests fail.** A guard that passes
against its own mutation is not a guard. If a test still passes with
`isGoogleSheets` forced to `true`, it is testing something else.

### While you are in there

Check whether the same `IndexOf`-a-hostname style appears anywhere else in the
add-in's URL handling. If it does, report it — do not fix it in the same change.

---

## What NOT to do

- **Do not modify `C:\Users\User01\source\repos\ScrapeX`.** Another session owns
  it and has work in flight.
- **Do not broaden this into a security review of the add-in.** One finding, one
  repair, one commit.
- **Do not add authentication to the fetch.** The sources are published public
  URLs by design; that is a separate decision and not yours to take here.
- Do not rename error codes or change severities that are not part of this fix.

---

## When you are done, report back these five things

The owner will carry your answer to the ScrapeX session, which has to react to
it. Be precise:

1. **Confirmed or refuted**, with the file:line that settled it — including your
   answer to "who is the attacker and what access do they need".
2. Which host rule you chose (point 1 above) and why.
3. Whether an impostor address now produces a finding, and at what severity and
   code.
4. The mutation you ran and which test caught it.
5. Whether you found the same style elsewhere.

### And one thing ScrapeX needs from you specifically

ScrapeX reproduces your validator deliberately, so that its Console warns in
exactly the cases you do. That copy lives in
`extension/addin-contract.js` as `readsUriAsGoogleSheets`, and it is documented
as reproducing a defect **on purpose**. There is a test in
`extension/tests/datasource-rules.test.mjs` named

> *"the mirror still agrees with the add-in, INCLUDING where it is wrong"*

which is designed to **fail the day you fix this**. That failure is the signal,
not a bug — its comment says the impostor warning should then be reconsidered
rather than deleted for lack of coverage.

So: **say clearly in your report that the behaviour changed.** There is no
`behaviourVersion` in this repository yet (a separate handoff,
`docs/HANDOFF-mbiXaddin-contract-producer.md`, proposes adding one for exactly
this reason). Until it exists, your written report is the only mechanism that
tells ScrapeX its reading has gone stale.
