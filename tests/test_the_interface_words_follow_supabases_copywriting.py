"""The interface's words follow Supabase's copywriting rules, at the pin (#744, #1040).

`apps/design-system/content/docs/copywriting.mdx@86c813ec` is the source, and only the rules a
machine can check without judgement are checked here:

- Page names are title case (`:128-130`, `:232`). A page name is a rail item, a Console rail
  item, the accessible name and tooltip each carries, and every `h1`.
- Section labels and in-page headings are sentence case (`:140-146`, `:231`). They are
  `h2` to `h6` and `legend`.
- A loading state names what is happening, never "Please wait...", "Processing..." or a
  bare "Loading..." (`:180-184`), and marketing words are not used: "easily", "simply",
  "powerful" (`:215-219`).

WHAT IS READ. The words a person sees: HTML text and the `title`, `aria-label`,
`placeholder` and `alt` attributes, with HTML and Jinja comments removed, and the string
literals in the panel's JavaScript with its comments removed. A heading built by JavaScript
is not a heading here; its string is still read for the banned words.

TODAY'S OFFENDERS ARE LISTED BY NAME, and the check is an equality, so the list only
shrinks: a new offender fails, and so does one that was fixed and not taken off.
"""
from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path

import pytest

pytestmark = pytest.mark.extension

ROOT = Path(__file__).resolve().parent.parent
HTML_FILES = sorted([*(ROOT / "extension").glob("*.html"), *(ROOT / "scrapex" / "webui" / "templates").glob("*.html")])
JS_FILES = sorted((ROOT / "extension").glob("*.js"))
VISIBLE_ATTRIBUTES = ("title", "aria-label", "placeholder", "alt")

BANNED = (
    ("please wait", re.compile(r"\bplease wait\b", re.I)),
    ("processing...", re.compile(r"\bprocessing(?:\.\.\.|…)", re.I)),
    ("bare loading...", re.compile(r"\bloading(?:\.\.\.|…)", re.I)),
    ("easily", re.compile(r"\beasily\b", re.I)),
    ("simply", re.compile(r"\bsimply\b", re.I)),
    ("powerful", re.compile(r"\bpowerful\b", re.I)),
)

# Words title case leaves lower-case inside a name ("Choose a Data Source").
SMALL_WORDS = frozenset("a an and as at but by for in nor of on or per the to vs via with".split())
# Names that keep their capital inside sentence case. Supabase's own list is at :233-235;
# these are the ones this product's text uses. An acronym (CSV) or a word with a capital
# after its first letter (ScrapeX) keeps its case without being listed.
PROPER_NOUNS = frozenset({
    "Supabase", "Google", "Chrome", "Excel", "Sheet", "Sheets", "Apps", "Script", "Finance",
    "Postgres", "SQLite", "Tabulator", "Arabic", "English", "Microsoft", "Windows", "Drive",
})


def _jinja_free(text: str) -> str:
    """Template text with Jinja's comments, statements and expressions blanked, lines kept."""
    blank = lambda m: re.sub(r"[^\n]", " ", m.group(0))  # noqa: E731
    return re.sub(r"\{#.*?#\}|\{%.*?%\}|\{\{.*?\}\}", blank, text, flags=re.S)


class _Reader(HTMLParser):
    """Visible text and attributes, and the text of every element whose role is judged."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack: list[tuple[str, dict]] = []
        self.visible: list[tuple[int, str]] = []
        self.roles: list[tuple[int, str, str]] = []  # (line, role, text)
        self._open: list[list] = []  # [role, line, parts] for each judged element still open

    def _role(self, tag: str, attrs: dict) -> str | None:
        classes = attrs.get("class", "").split()
        # The profile's h1 is a greeting ("Hi, <name>"), and app.html says so beside it: it
        # names a person, not a page.
        if tag == "h1" and "profile-greeting" not in classes:
            return "page name"
        if tag == "button" and {"rail-item", "rail-link"} & set(classes):
            return "page name"
        if tag in ("h2", "h3", "h4", "h5", "h6", "legend"):
            return "heading"
        return None

    VOID = frozenset("area base br col embed hr img input link meta source track wbr".split())

    def _attributes(self, tag, attrs):
        attrs = {k: v or "" for k, v in attrs}
        line, role = self.getpos()[0], self._role(tag, attrs)
        for name in VISIBLE_ATTRIBUTES:
            if attrs.get(name, "").strip():
                self.visible.append((line, attrs[name]))
                if role == "page name" and name in ("aria-label", "title"):
                    self.roles.append((line, role, attrs[name]))
        return attrs, line, role

    def handle_starttag(self, tag, attrs):
        attrs, line, role = self._attributes(tag, attrs)
        if tag not in self.VOID:
            self.stack.append((tag, attrs))
            self._open.append([role, line, []] if role else None)

    def handle_startendtag(self, tag, attrs):
        self._attributes(tag, attrs)  # `<br/>`, `<use/>`: attributes, and nothing to close

    def handle_endtag(self, tag):
        if tag not in (t for t, _ in self.stack):
            return  # a stray end tag closes nothing
        while self.stack:
            open_tag, _ = self.stack.pop()
            judged = self._open.pop()
            if judged:
                text = " ".join("".join(judged[2]).split())
                if text:
                    self.roles.append((judged[1], judged[0], text))
            if open_tag == tag:
                break

    def handle_data(self, data):
        if any(t in ("script", "style") for t, _ in self.stack):
            return
        if data.strip():
            self.visible.append((self.getpos()[0], data))
        for judged in self._open:
            if judged:
                judged[2].append(data)


def _read_html(path: Path) -> _Reader:
    reader = _Reader()
    reader.feed(_jinja_free(path.read_text(encoding="utf-8")))
    reader.close()
    return reader


def _code_end(source: str, j: int) -> int:
    """Index just past the `}` closing a template literal's `${` whose code starts at j."""
    depth = 1
    while j < len(source) and depth:
        if source[j] in "\"'`":
            j = _string_end(source, j)
            continue
        depth += {"{": 1, "}": -1}.get(source[j], 0)
        j += 1
    return j


def _string_end(source: str, j: int) -> int:
    """Index just past the string literal whose opening quote is at j."""
    quote, j = source[j], j + 1
    while j < len(source) and source[j] != quote:
        if source[j] == "\\":
            j += 2
        elif quote == "`" and source.startswith("${", j):
            j = _code_end(source, j + 2)
        elif quote != "`" and source[j] == "\n":
            return j  # an unterminated quote ends at its line
        else:
            j += 1
    return j + 1


def _js_strings(source: str) -> list[str]:
    """The contents of every string literal in `source`, with comments skipped.

    A template literal's `${...}` is code: its place in the text becomes a space, and the
    strings inside it are read as strings of their own, because `${x || "not built yet"}`
    puts that fallback on the screen. A regular-expression literal is not recognised, so a
    quote inside one could open a false string; the unit tests below pin what is handled.
    """
    out, i, n = [], 0, len(source)
    while i < n:
        if source.startswith("//", i):
            i = n if source.find("\n", i) < 0 else source.find("\n", i)
        elif source.startswith("/*", i):
            i = n if source.find("*/", i + 2) < 0 else source.find("*/", i + 2) + 2
        elif source[i] in "\"'`":
            end = _string_end(source, i)
            body, text, j = source[i + 1:end - 1], [], 0
            while j < len(body):
                if source[i] == "`" and body.startswith("${", j):
                    close = _code_end(body, j + 2)
                    out.extend(_js_strings(body[j + 2:close - 1]))
                    text.append(" ")
                    j = close
                elif body[j] == "\\":
                    text.append(body[j:j + 2])
                    j += 2
                else:
                    text.append(body[j])
                    j += 1
            out.append("".join(text))
            i = end
        else:
            i += 1
    return out


def _words(text: str) -> list[str]:
    """The words whose case is judged. A token holding `.`, `_`, `/`, `@` or a digit is
    technical -- `robots.txt`, `job_ref` -- and keeps whatever case it has."""
    return [w for token in text.split() if not re.search(r"[._/@0-9]", token)
            for w in re.findall(r"[A-Za-z][A-Za-z'’-]*", token)]


def _is_title_case(text: str) -> bool:
    words = _words(text)
    for index, word in enumerate(words):
        if index and index < len(words) - 1 and word.lower() in SMALL_WORDS:
            continue
        if not word[0].isupper():
            return False
    return True


def _is_sentence_case(text: str) -> bool:
    words = _words(text)
    if not words:
        return True
    if not words[0][0].isupper():
        return False
    for word in words[1:]:
        if not word[0].isupper():
            continue
        # An acronym, a name like ScrapeX, or a listed proper noun keeps its capital.
        if word.isupper() and len(word) > 1 or any(ch.isupper() for ch in word[1:]) or word in PROPER_NOUNS:
            continue
        return False
    return True


def _found() -> Counter:
    """How many times each (file, rule, text) offence occurs in the interface today.

    Counted, not collected as a set, so a second copy of a listed offence in the same file
    is a new offence."""
    found = Counter()
    for path in HTML_FILES:
        relative = path.relative_to(ROOT).as_posix()
        reader = _read_html(path)
        for _, text in reader.visible:
            for rule, pattern in BANNED:
                if pattern.search(text):
                    found[(relative, rule, " ".join(text.split()))] += 1
        for _, role, text in reader.roles:
            if role == "page name" and not _is_title_case(text):
                found[(relative, "page name in title case", text)] += 1
            if role == "heading" and not _is_sentence_case(text):
                found[(relative, "heading in sentence case", text)] += 1
    for path in JS_FILES:
        relative = path.relative_to(ROOT).as_posix()
        for text in _js_strings(path.read_text(encoding="utf-8")):
            for rule, pattern in BANNED:
                if pattern.search(text):
                    found[(relative, rule, " ".join(text.split()))] += 1
    return found


# TODAY'S OFFENDERS, written down so the next one fails. Fix one and take it off here in the
# same change; #1071 and #743 are where most of them are fixed.
OFFENDERS: dict[tuple[str, str, str], int] = {
    ('extension/addin-contract.js', 'simply', 'the mappings simply never run'): 1,
    ('extension/app.html', 'bare loading...', 'Loading…'): 2,
    ('extension/app.html', 'heading in sentence case', 'Browse Data'): 1,
    ('extension/app.html', 'page name in title case', 'Edit source'): 1,
    ('extension/app.html', 'page name in title case', 'Manage account'): 1,
    ('extension/app.html', 'page name in title case', 'Workspace pages'): 3,
    ('extension/app.html', 'please wait', 'Please wait'): 1,
    ('extension/app.js', 'please wait', 'Please wait'): 1,
    ('extension/app.js', 'simply', '<div class="muted text-sm mt-2">No capability is missing yet — the extension is simply behind.</div>'): 1,
    ('extension/console.html', 'page name in title case', 'Build a table'): 1,
    ('extension/datamap-rules.js', 'simply', 'are not an error and nothing reports them at sync time — they simply'): 1,
    ('extension/exportviews-rules.js', 'simply', 'simply never appears anywhere and nothing reports it missing.'): 1,
    ('extension/ribboncontrols-rules.js', 'simply', 'Nothing reports it: the row is simply never selected by any menu or'): 1,
    ('extension/ribboncontrols-rules.js', 'simply', 'reports it; the export simply contains more than it should.'): 1,
    ('scrapex/webui/templates/data.html', 'page name in title case', 'Browse your datasets'): 1,
    ('scrapex/webui/templates/database_unavailable.html', 'page name in title case', 'This page needs a database it cannot read'): 1,
    ('scrapex/webui/templates/datasets.html', 'page name in title case', 'Generic datasets'): 1,
    ('scrapex/webui/templates/excel.html', 'page name in title case', 'Build your Excel workbook'): 1,
    ('scrapex/webui/templates/google_finance_dataset.html', 'page name in title case', 'Google Finance exchange rates'): 1,
    ('scrapex/webui/templates/history.html', 'page name in title case', 'Crawl history'): 1,
    ('scrapex/webui/templates/manage.html', 'page name in title case', 'Add a source'): 1,
    ('scrapex/webui/templates/overview.html', 'page name in title case', 'Your data pipeline'): 1,
    ('scrapex/webui/templates/review.html', 'page name in title case', 'Review queue'): 1,
    ('scrapex/webui/templates/schema.html', 'heading in sentence case', "The Data page's columns"): 1,
}


def test_no_new_words_break_supabases_copywriting():
    found, listed = _found(), Counter(OFFENDERS)
    assert found == listed, (
        "the interface's words and OFFENDERS disagree (copywriting.mdx@86c813ec):\n"
        f"  new, not listed: {sorted((found - listed).items())}\n"
        f"  listed, and no longer there: {sorted((listed - found).items())}\n"
        "Word a new string the Supabase way. Take a fixed one off the list in the same change."
    )


def test_the_reader_finds_what_it_judges():
    """Without this, a reader that stopped finding the rail, the headings or the strings would pass."""
    roles = [role for path in HTML_FILES for _, role, _ in _read_html(path).roles]
    strings = sum(len(_js_strings(p.read_text(encoding="utf-8"))) for p in JS_FILES)
    assert roles.count("page name") >= 40, f"found only {roles.count('page name')} page names"
    assert roles.count("heading") >= 100, f"found only {roles.count('heading')} headings"
    assert strings >= 5000, f"found only {strings} string literals in the panel's JavaScript"


@pytest.mark.parametrize("source, expected", [
    ('const a = "Loading…"; // Please wait', ["Loading…"]),
    ("/* 'not a string' */ const b = 'kept';", ["kept"]),
    ('const c = "a // not a comment";', ["a // not a comment"]),
    ("const d = `before ${x || 'fallback'} after`;", ["fallback", "before   after"]),
    ("const f = `a ${g({k: '}'})} b`;", ["}", "a   b"]),
    ('const e = "it\\"s";', ['it\\"s']),
])
def test_the_script_reader_keeps_strings_and_drops_comments(source, expected):
    assert _js_strings(source) == expected


@pytest.mark.parametrize("text, title, sentence", [
    ("Choose a Data Source", True, False),
    ("Edit source", False, True),
    ("Google Finance", True, True),
    ("Welcome to ScrapeX", True, True),
    ("Set Up Authentication", True, False),
    ("CSV export", False, True),
    ("robots.txt", True, True),
    ("Disconnect Drive?", True, True),
])
def test_the_case_rules_read_the_way_copywriting_mdx_does(text, title, sentence):
    assert _is_title_case(text) is title
    assert _is_sentence_case(text) is sentence
