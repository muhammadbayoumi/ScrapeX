"""How often each memory lesson broke again after it was written down.

    python -m tools.recurrence_scan [--memory DIR] [--projects DIR] [--json]

WHY THIS EXISTS (#1104). A lesson in auto-memory is a sentence, and nothing counts
whether the sentence works. "Write the script, don't heredoc it" failed five more
times after it was recorded, in four sessions, and its note never changed, because
nobody appends a recurrence to a note. A lesson that breaks twice has earned a
barrier -- a hook, a failing test -- and this is the counter that says which ones.

WHAT IT READS, and it writes nothing:

  * every memory note's frontmatter, for `metadata.failure_signature`:

        failure_signature:
          tool: Bash            # a tool name, a list of names, shell (Bash and PowerShell,
                                # the default) or any; names are case-sensitive
          command: '<regex>'    # optional: searched in the command (or file path) of the call
          result: '<regex>'     # optional: searched in the tool's output
          kind: failure         # failure (default when `result` is set) | shape
          caveat: '<text>'      # optional: how to read the count, printed beside it

    A `failure` signature matches evidence that the lesson broke. A `shape`
    signature matches only the form a lesson forbids, which is not the same thing:
    a shape the note forbids "when X" is a failure only if X held. Shapes are
    counted and labelled, and never flagged as a barrier candidate.

  * every session transcript under the projects directory whose folder name
    contains ScrapeX -- main sessions, subagents and workflow agents alike. A tool
    call recorded twice in one transcript counts once.

WHEN A LESSON WAS RECORDED is the Write, in any transcript, that CREATED a file with
the note's name inside a `memory` folder under the projects directory (its result
reads "File created successfully"). It is matched by name, not by the path being
scanned, so a scratch copy of the notes is dated by the real lesson. Nothing else
can stand in for it: the note's `metadata.modified` moves on every edit, and so does
the file's creation time, because the Write tool replaces the file. So a lesson
whose creating Write no longer survives has an UNKNOWN start: the report gives its
total matches, never a before/after split, and never flags it. The Write tool's two
wordings, created and updated, are parsed and nothing else is assumed: a write of a
note whose result matches neither is named in the reason, because a Claude Code
release that rewords them would otherwise turn every lesson "unknown" in silence.

A SIGNATURE MUST MATCH THE ERROR'S OWN FORM, NOT ITS TEXT ANYWHERE. Sessions that
read old transcripts print old errors again, and a regex that matches the text
anywhere counts every such reading as a new failure. Anchor on the line the tool
itself prints (`(?m)^...`); the calibration in #1104 measured this on real data.

AN EMPTY SCAN IS A CLAIM ABOUT THE SCANNER. No transcript, or no tool call parsed
from any of them, exits 1 and says so; it never reports "nothing recurred".
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

SHELLS = ("Bash", "PowerShell")
FRONTMATTER = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n", re.DOTALL)
BARRIER_AT = 2
KEYS = {"tool", "command", "result", "kind", "caveat"}


@dataclass
class Signature:
    tools: tuple[str, ...] | None  # None means any tool
    command: re.Pattern | None
    result: re.Pattern | None
    kind: str
    caveat: str | None = None
    named: tuple[str, ...] = ()  # the names written literally; each must match some call


@dataclass
class Note:
    name: str
    path: Path
    signature: Signature | None = None
    error: str | None = None


@dataclass
class Call:
    when: dt.datetime
    session: str
    tool: str
    target: str  # the command for a shell, the file path for Write/Edit
    result: str


@dataclass
class Row:
    note: Note
    recorded: dt.datetime | None  # None: no creating Write survives, so the split is unknown
    recorded_from: str
    before: int = 0
    after: int = 0
    total: int = 0
    sessions_after: set[str] = field(default_factory=set)
    last: dt.datetime | None = None


def parse_signature(raw: object) -> Signature:
    """A signature from frontmatter, or ValueError saying what is wrong with it."""
    if not isinstance(raw, dict):
        raise ValueError("failure_signature is not a mapping")
    unknown = set(raw) - KEYS
    if unknown:
        raise ValueError(f"unknown keys {sorted(unknown)}")
    tool = raw.get("tool", "shell")
    if isinstance(tool, list) and tool and all(isinstance(t, str) and t for t in tool):
        if {"shell", "any"} & set(tool):
            raise ValueError("shell and any stand alone; they cannot be listed with tool names")
        tools = named = tuple(dict.fromkeys(tool))
    elif isinstance(tool, str) and tool:
        tools = {"shell": SHELLS, "any": None}.get(tool, (tool,))
        named = () if tool in ("shell", "any") else (tool,)
    else:
        raise ValueError(f"tool must be a tool name or a list of them, not {tool!r}")
    patterns = {}
    for key in ("command", "result"):
        value = raw.get(key)
        if value is None:
            patterns[key] = None
            continue
        if not isinstance(value, str) or not value:
            raise ValueError(f"{key} is not a non-empty string")
        try:
            patterns[key] = re.compile(value)
        except re.error as exc:
            raise ValueError(f"{key} is not a valid regex: {exc}") from exc
    if patterns["command"] is None and patterns["result"] is None:
        raise ValueError("needs a command or a result pattern")
    kind = raw.get("kind", "failure" if patterns["result"] else "shape")
    if kind not in ("failure", "shape"):
        raise ValueError(f"kind must be failure or shape, not {kind!r}")
    if kind == "failure" and patterns["result"] is None:
        raise ValueError("a failure signature needs a result pattern: a command alone is a shape")
    caveat = raw.get("caveat")
    if caveat is not None and not isinstance(caveat, str):
        raise ValueError("caveat is not a string")
    return Signature(tools, patterns["command"], patterns["result"], kind, caveat, named)


def load_notes(memory: Path) -> list[Note]:
    notes = []
    for path in sorted(memory.glob("*.md")):
        if path.name == "MEMORY.md":
            continue
        note = Note(path.stem, path)
        match = FRONTMATTER.match(path.read_text(encoding="utf-8"))
        try:
            if not match:
                raise ValueError("no frontmatter (a byte-order mark before the first --- hides it)")
            front = yaml.safe_load(match.group(1)) or {}
            metadata = front.get("metadata") if isinstance(front, dict) else None
            if metadata is not None and not isinstance(metadata, dict):
                raise ValueError("metadata is not a mapping")
            raw = (metadata or {}).get("failure_signature")
            if raw is not None:
                note.signature = parse_signature(raw)
        except (ValueError, yaml.YAMLError) as exc:
            note.error = str(exc).splitlines()[0]
        notes.append(note)
    return notes


def _when(stamp: str) -> dt.datetime | None:
    try:
        return dt.datetime.fromisoformat(stamp)
    except ValueError:
        return None


def _text(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(p.get("text", "") for p in content if isinstance(p, dict))
    return ""


def transcripts(projects: Path) -> list[Path]:
    return sorted(
        path
        for folder in projects.iterdir() if folder.is_dir() and "ScrapeX" in folder.name
        for path in folder.rglob("*.jsonl") if path.name != "journal.jsonl"
    )


def read_calls(path: Path, projects: Path) -> list[Call]:
    """Every tool call in one transcript, paired with its result by tool_use_id,
    once each: a transcript can record the same call more than once."""
    parts = path.relative_to(projects).parts
    session = parts[1] if len(parts) > 2 else path.stem
    pending: dict[str, tuple[dt.datetime, str, str]] = {}
    done: set[str] = set()
    calls = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            if '"tool_use"' not in line and '"tool_result"' not in line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            message = record.get("message")
            when = _when(record.get("timestamp") or "")
            if not isinstance(message, dict) or not isinstance(message.get("content"), list) or when is None:
                continue
            for part in message["content"]:
                if not isinstance(part, dict):
                    continue
                use_id = part.get("id") if part.get("type") == "tool_use" else part.get("tool_use_id")
                if not use_id or use_id in done:
                    continue
                if part.get("type") == "tool_use":
                    given = part.get("input") or {}
                    target = given.get("command") or given.get("file_path") or ""
                    pending.setdefault(use_id, (when, part.get("name", ""), str(target)))
                elif part.get("type") == "tool_result" and use_id in pending:
                    started, tool, target = pending.pop(use_id)
                    done.add(use_id)
                    calls.append(Call(started, session, tool, target, _text(part.get("content"))))
    return calls


def _norm(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def _writes_this_note(call: Call, filename: str, projects: str) -> bool:
    """A Write or Edit of `<projects>/<any project>/memory/<filename>`."""
    if call.tool not in ("Write", "Edit") or not call.target:
        return False
    target = _norm(call.target)
    return (os.path.basename(target) == os.path.normcase(filename)
            and os.path.basename(os.path.dirname(target)) == "memory"
            and target.startswith(projects + os.sep))


CREATED = "File created successfully"  # how the Write tool reports a new file
UPDATED = "has been updated successfully"  # how Write and Edit report changing one


def scan(notes: list[Note], calls: list[Call], projects: Path) -> list[Row]:
    root = _norm(str(projects))
    seen_tools = {c.tool for c in calls}
    rows = []
    for note in notes:
        sig = note.signature
        unused = [t for t in sig.named if t not in seen_tools] if sig is not None else []
        if unused:
            note.error = (f"tool {', '.join(unused)} matches none of the {len(calls)} calls in the "
                          "transcripts; tool names are case-sensitive")
            note.signature = sig = None
        writes = [c for c in calls if _writes_this_note(c, note.path.name, root)]
        created = [c.when for c in writes if c.tool == "Write" and c.result.startswith(CREATED)]
        unread = [c.result for c in writes if not c.result.startswith(CREATED) and UPDATED not in c.result]
        if created:
            row = Row(note, min(created), "created in a transcript")
        elif unread:
            row = Row(note, None, "a write of the note printed a result this scanner does not recognise "
                                  f"({unread[0][:60]!r}); its reading of the Write tool's result is out of date")
        elif writes:
            row = Row(note, None, "the earliest surviving write is an update, so the lesson is older")
        else:
            row = Row(note, None, "no write of the note survives in any transcript")
        if sig is not None:
            for call in calls:
                if sig.tools is not None and call.tool not in sig.tools:
                    continue
                if sig.command is not None and not sig.command.search(call.target):
                    continue
                if sig.result is not None and not sig.result.search(call.result):
                    continue
                row.total += 1
                if row.recorded is None:
                    continue
                if call.when < row.recorded:
                    row.before += 1
                else:
                    row.after += 1
                    row.sessions_after.add(call.session)
                    row.last = max(row.last or call.when, call.when)
        rows.append(row)
    return rows


def report(rows: list[Row]) -> str:
    measured = sorted((r for r in rows if r.note.signature), key=lambda r: (-r.after, -r.total))
    lines = [f"{'lesson':50s} {'kind':7s} {'recorded':10s} {'before':>6s} {'after':>5s} "
             f"{'total':>5s} {'sessions':>8s}  last"]
    for r in measured:
        known = r.recorded is not None
        flag = ("  <- barrier candidate"
                if known and r.note.signature.kind == "failure" and r.after >= BARRIER_AT else "")
        last = r.last.date().isoformat() if r.last else "-"
        recorded = r.recorded.date().isoformat() if known else "unknown"
        before, after = (f"{r.before:6d}", f"{r.after:5d}") if known else (f"{'?':>6s}", f"{'?':>5s}")
        lines.append(f"{r.note.name[:50]:50s} {r.note.signature.kind:7s} {recorded:10s} {before} {after} "
                     f"{r.total:5d} {len(r.sessions_after):8d}  {last}{flag}")
        if r.note.signature.caveat:
            lines.append(f"    caveat: {r.note.signature.caveat}")
    for r in measured:
        if r.recorded is None:
            lines.append(f"START UNKNOWN {r.note.name}: {r.recorded_from}; counted in total only, never flagged")
    for r in rows:
        if r.note.error:
            lines.append(f"UNREADABLE SIGNATURE {r.note.name}: {r.note.error}")
    unmeasured = [r.note.name for r in rows if not r.note.signature and not r.note.error]
    lines.append(f"{len(measured)} lessons measured, {len(unmeasured)} with no failure_signature: "
                 + ", ".join(unmeasured))
    return "\n".join(lines)


def as_json(rows: list[Row]) -> str:
    return json.dumps([{
        "lesson": r.note.name,
        "kind": r.note.signature.kind if r.note.signature else None,
        "caveat": r.note.signature.caveat if r.note.signature else None,
        "error": r.note.error,
        "recorded": r.recorded.isoformat() if r.recorded else None,
        "recorded_from": r.recorded_from,
        "before": r.before if r.recorded else None,
        "after": r.after if r.recorded else None,
        "total": r.total,
        "sessions_after": sorted(r.sessions_after),
        "last": r.last.isoformat() if r.last else None,
    } for r in rows], indent=1)


def default_memory(projects: Path) -> Path | None:
    """Claude Code keys auto-memory to the MAIN checkout, whichever worktree runs this:
    its folder is that checkout's absolute path with every other character a dash."""
    try:
        common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                cwd=Path(__file__).resolve().parent, capture_output=True,
                                text=True, check=True).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return None
    return projects / project_folder(Path(common).parent) / "memory"


def project_folder(checkout: Path) -> str:
    return re.sub(r"[^A-Za-z0-9]", "-", str(checkout))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--projects", type=Path, default=Path.home() / ".claude" / "projects")
    parser.add_argument("--memory", type=Path, help="default: this checkout's auto-memory folder")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    args.projects = args.projects.resolve()  # a relative path would never match a Write's absolute one
    if args.memory is None:
        args.memory = default_memory(args.projects)
        if args.memory is None:
            print("recurrence_scan: git could not name the main checkout; pass --memory", file=sys.stderr)
            return 1

    files = transcripts(args.projects) if args.projects.is_dir() else []
    calls = [call for path in files for call in read_calls(path, args.projects)]
    if not files or not calls:
        print(f"recurrence_scan: found {len(files)} transcripts and {len(calls)} tool calls under "
              f"{args.projects} -- the scanner is broken or pointed at the wrong place; an empty "
              "scan is not evidence that nothing recurred", file=sys.stderr)
        return 1
    notes = load_notes(args.memory) if args.memory.is_dir() else []
    if not notes:
        print(f"recurrence_scan: no memory notes in {args.memory}", file=sys.stderr)
        return 1
    rows = scan(notes, calls, args.projects)
    print(as_json(rows) if args.json else report(rows))
    print(f"scanned {len(files)} transcripts, {len(calls)} tool calls", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
