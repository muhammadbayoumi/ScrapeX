// One DataSource row, judged as the add-in judges it.
//
// Every expectation here is the add-in's behaviour read out of its C#, not a
// preference. Where a rule looks strange — a blank PROFILE_KEY that both WORKS
// and records an Error, a two-letter typo that blocks every user — the strange
// part is the add-in's and the test says so, because that is exactly the kind of
// rule someone later "corrects" into something more reasonable and wrong.

import { test } from "node:test";
import assert from "node:assert/strict";

import { checkSourceUri, checkDataSourceRow, stopsThisSource, switchedOff,
         suggestedKey } from "../datasource-rules.js";
import { readsUriAsGoogleSheets } from "../addin-contract.js";

const PUBLISHED =
  "https://docs.google.com/spreadsheets/d/e/2PACX-1vAAA/pub?gid=223498986&single=true&output=tsv";

/** A row with nothing wrong with it — the control for every test below. */
const sound = (over = {}) => ({
  SOURCE_KEY: "T_DIESEL_P_DIESEL",
  TARGET_ENTITY_KEY: "T_DIESEL",
  PROFILE_KEY: "P_DIESEL",
  SOURCE_URI: PUBLISHED,
  SOURCE_REGION: "EG",
  DISPLAY_LABEL: "Diesel prices",
  IS_ACTIVE: "True",
  ...over,
});

const world = (over = {}) => ({
  entities: ["T_DIESEL"],
  activeEntities: ["T_DIESEL"],
  profilesDefined: ["P_DIESEL"],
  others: [],
  ...over,
});

const check = (row, w = {}) => checkDataSourceRow(row, world(w));
const fields = (found) => found.map((f) => f.field);
const worst = (found) => found[0]?.severity;

// ---------------------------------------------------------------------------
// The control
// ---------------------------------------------------------------------------

test("a sound row produces nothing at all", () => {
  assert.deepEqual(check(sound()), [],
    "the checker invented a fault in a row the add-in is happy with, which is "
    + "how an owner learns to click past it");
});

test("and a sound row stops nothing", () => {
  assert.equal(stopsThisSource(check(sound())), false);
});

// ---------------------------------------------------------------------------
// SOURCE_KEY — Critical, and the add-in stops reading the row
// ---------------------------------------------------------------------------

test("no key abandons the row, so nothing else is reported", () => {
  const found = check(sound({SOURCE_KEY: "", TARGET_ENTITY_KEY: "", SOURCE_URI: ""}));

  assert.equal(found.length, 1,
    "three faults were listed for a row the add-in stops reading after the "
    + "first — a cascade about a row nobody reaches");
  assert.equal(found[0].severity, "Critical");
  assert.equal(found[0].field, "SOURCE_KEY");
  assert.match(found[0].fix, /TARGET_ENTITY_KEY.*PROFILE_KEY/);
});

test("a duplicate key says WHERE the twin is and what it costs", () => {
  const found = check(sound(), {
    others: [{SOURCE_KEY: "t_diesel_p_diesel", _row: 9}],   // case-insensitive
  });

  const key = found.filter((f) => f.field === "SOURCE_KEY");
  assert.equal(key.length, 1);
  assert.equal(key[0].severity, "Error");
  assert.match(key[0].detail, /row 9/);
  assert.match(key[0].detail, /delete another's rows/);
});

test("a row does not collide with itself", () => {
  // `others` is every OTHER row on purpose. Passing the whole sheet would make
  // every row a duplicate of itself the moment it is opened for editing.
  assert.deepEqual(check(sound(), {others: []}).filter((f) => f.field === "SOURCE_KEY"), []);
});

// ---------------------------------------------------------------------------
// TARGET_ENTITY_KEY — two different faults with the same symptom
// ---------------------------------------------------------------------------

test("naming no table at all", () => {
  const found = check(sound({TARGET_ENTITY_KEY: ""}));
  assert.equal(found[0].severity, "Critical");
  assert.equal(found[0].field, "TARGET_ENTITY_KEY");
});

test("naming a table that does not exist — SILENTLY dropped by the add-in", () => {
  const found = check(sound({TARGET_ENTITY_KEY: "T_TYPO"}))
    .filter((f) => f.field === "TARGET_ENTITY_KEY");

  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /nothing says why/,
    "the message does not tell the owner the failure is silent, which is the "
    + "only reason this one is hard to find");
});

test("naming a table that exists and is switched OFF", () => {
  // Resolves, and still never syncs. Same symptom, different cause, and an
  // owner told only "it never syncs" would go looking at the wrong sheet.
  const found = check(sound(), {activeEntities: []})
    .filter((f) => f.field === "TARGET_ENTITY_KEY");

  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Warning");
  assert.match(found[0].detail, /not active/);
});

test("the entity match is case-insensitive, as the add-in's is", () => {
  assert.deepEqual(
    check(sound({TARGET_ENTITY_KEY: "t_diesel"}))
      .filter((f) => f.field === "TARGET_ENTITY_KEY"), []);
});

// ---------------------------------------------------------------------------
// PROFILE_KEY — the rule that is true twice over
// ---------------------------------------------------------------------------

test("a BLANK profile works AND is reported, because both are true", () => {
  // It resolves to the entity key, so the source syncs. The add-in records an
  // Error about it anyway. Saying only one half sends the owner to fix
  // something that works, or to ignore a message that is real.
  const found = check(sound({PROFILE_KEY: ""}), {profilesDefined: ["T_DIESEL"]})
    .filter((f) => f.field === "PROFILE_KEY");

  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /resolves to "T_DIESEL"/);
  assert.match(found[0].detail, /It works; it is noisy/);
  assert.match(found[0].fix, /Write T_DIESEL here/);
});

test('"DEFAULT" resolves the same way and is NOT reported', () => {
  // Explicit and legal. Complaining about it would be inventing a rule.
  for (const spelling of ["DEFAULT", "default", "Default"]) {
    assert.deepEqual(
      check(sound({PROFILE_KEY: spelling}), {profilesDefined: ["T_DIESEL"]})
        .filter((f) => f.field === "PROFILE_KEY"), [],
      `"${spelling}" was reported`);
  }
});

test("a profile no DataMap defines fails the ingest, and says so plainly", () => {
  const found = check(sound({PROFILE_KEY: "P_NOWHERE"}))
    .filter((f) => f.field === "PROFILE_KEY");

  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /FAILS to ingest/);
});

test("a BLANK profile whose resolved name has no mappings is caught too", () => {
  // Both halves of the rule at once: blank is noisy, and the thing it resolves
  // to does not exist. The first version checked only the literal value and so
  // missed this entirely.
  const found = check(sound({PROFILE_KEY: ""}), {profilesDefined: ["SOMETHING_ELSE"]})
    .filter((f) => f.field === "PROFILE_KEY");

  assert.equal(found.length, 2);
  assert.ok(found.some((f) => /FAILS to ingest/.test(f.detail)));
});

// ---------------------------------------------------------------------------
// The address — where an owner goes wrong most often
// ---------------------------------------------------------------------------

test("the published TSV shape passes clean", () => {
  assert.deepEqual(checkSourceUri(PUBLISHED), []);
});

test("no address is Critical, and the fix is the four menu steps", () => {
  const found = checkSourceUri("");
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Critical");
  assert.match(found[0].fix, /Publish to web/);
});

test("THE COMMONEST MISTAKE — a Google address with no TSV format", () => {
  // The add-in downloads a web page, sniffs `<!DOCTYPE`, and reports a PARSE
  // failure — so the owner goes looking at the data instead of the address.
  const found = checkSourceUri(
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vAAA/pub?gid=1&single=true");

  const format = found.filter((f) => /output=tsv/.test(f.fix));
  assert.equal(format.length, 1);
  assert.equal(format[0].severity, "Error");
  assert.match(format[0].detail, /WEB PAGE/);
});

test("format=tsv is accepted as well as output=tsv", () => {
  assert.deepEqual(
    checkSourceUri("https://docs.google.com/spreadsheets/d/x/pub?gid=1&format=tsv"), []);
});

test("a Google address with no gid reads whichever tab is first", () => {
  const found = checkSourceUri(
    "https://docs.google.com/spreadsheets/d/e/2PACX-1vAAA/pub?single=true&output=tsv");

  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Warning");
  assert.match(found[0].detail, /FIRST tab/);
});

test("the browser's own edit link is refused before anything downloads", () => {
  const found = checkSourceUri(
    "https://docs.google.com/spreadsheets/d/1AbCdEf/edit#gid=0");
  assert.ok(found.some((f) => f.severity === "Error"));
});

test("neither a web address nor a path stops there", () => {
  for (const bad of ["ftp://host/file.tsv", "just-a-name.tsv", "sheet1"]) {
    const found = checkSourceUri(bad);
    assert.equal(found.length, 1, `${bad} produced ${found.length} findings`);
    assert.match(found[0].detail, /neither a web address nor a file path/);
  }
});

test("a local path is allowed, in all three shapes the add-in accepts", () => {
  for (const path of ["/srv/data/prices.tsv", "C:\\data\\prices.csv",
                      "\\\\server\\share\\prices.txt"]) {
    assert.deepEqual(checkSourceUri(path), [], `${path} was refused`);
  }
});

test("a local path with no data extension is only a warning", () => {
  const found = checkSourceUri("C:\\data\\prices");
  assert.equal(found.length, 1);
  assert.equal(found[0].severity, "Warning");
});

test("a host with no dot is suspected, not refused", () => {
  const found = checkSourceUri("http://localhost/prices.tsv");
  assert.equal(found[0].severity, "Warning");
});

// ---------------------------------------------------------------------------
// The rest
// ---------------------------------------------------------------------------

test("a region typo blocks EVERY user, and the message says that", () => {
  const found = check(sound({SOURCE_REGION: "EGY"}))
    .filter((f) => f.field === "SOURCE_REGION");

  assert.equal(found.length, 1);
  assert.match(found[0].detail, /BLOCKS EVERY USER/,
    "a three-letter code reads as a harmless typo unless the consequence is "
    + "named beside it");
});

test("GLOBAL and any two letters are fine; blank is fine", () => {
  for (const region of ["GLOBAL", "global", "SA", "eg", ""]) {
    assert.deepEqual(
      check(sound({SOURCE_REGION: region})).filter((f) => f.field === "SOURCE_REGION"),
      [], `${region || "(blank)"} was reported`);
  }
});

test("no label means the source appears under its key", () => {
  const found = check(sound({DISPLAY_LABEL: ""}))
    .filter((f) => f.field === "DISPLAY_LABEL");
  assert.equal(found[0].severity, "Warning");
});

test("switched off is Info, not a fault — and it does not block", () => {
  const found = check(sound({IS_ACTIVE: "False"}));
  const off = found.filter((f) => f.field === "IS_ACTIVE");

  assert.equal(off[0].severity, "Info");
  assert.equal(switchedOff(found), true);
  assert.equal(stopsThisSource(found), false,
    "a deliberately disabled source was reported as a fault to fix");
});

test("a BLANK IS_ACTIVE is not off — nothing is reported", () => {
  // The add-in's default is TRUE. A Console that showed a blank as "off" would
  // tell the owner a source is disabled while it syncs every day.
  assert.deepEqual(
    check(sound({IS_ACTIVE: ""})).filter((f) => f.field === "IS_ACTIVE"), []);
});

test("Arabic counts, in both directions", () => {
  assert.equal(
    check(sound({IS_ACTIVE: "لا"})).filter((f) => f.field === "IS_ACTIVE").length, 1);
  assert.deepEqual(
    check(sound({IS_ACTIVE: "نعم"})).filter((f) => f.field === "IS_ACTIVE"), []);
});

test("a broken CONTEXT_PROPS silently loses every setting in it", () => {
  const found = check(sound({CONTEXT_PROPS: "{SkipRows: 2}"}))   // not JSON
    .filter((f) => f.field === "CONTEXT_PROPS");
  assert.equal(found[0].severity, "Error");
  assert.match(found[0].detail, /ignored/);
});

test("valid JSON that is not an object is refused too", () => {
  for (const bag of ["[1,2]", '"text"', "42", "null"]) {
    const found = check(sound({CONTEXT_PROPS: bag}))
      .filter((f) => f.field === "CONTEXT_PROPS");
    assert.equal(found.length, 1, `${bag} was accepted`);
  }
});

test("a good CONTEXT_PROPS passes", () => {
  assert.deepEqual(
    check(sound({CONTEXT_PROPS: '{"SkipRows": 2, "SyncFreq": "Daily"}'}))
      .filter((f) => f.field === "CONTEXT_PROPS"), []);
});

// ---------------------------------------------------------------------------
// Ordering and blocking
// ---------------------------------------------------------------------------

test("the worst is first, so a long list still leads with what breaks", () => {
  const found = check(sound({
    DISPLAY_LABEL: "", SOURCE_REGION: "EGY", TARGET_ENTITY_KEY: "T_TYPO",
  }));
  assert.equal(worst(found), "Error");
  assert.equal(found.at(-1).severity, "Warning");
});

test("SEVERITY IS NOT THE SAME QUESTION AS 'does anything come out'", () => {
  // The first version of this asked "is anything an Error" and, over the real
  // workbook, declared 13 of 17 sources blocked — every one of which syncs
  // daily. SyncManager does not gate on a DataSource row at all; it gates on
  // the per-entity report, which lists a mapping-less profile among the
  // warnings that explicitly do NOT block.
  // Recorded as an Error by the add-in, and the source still syncs: blank
  // PROFILE_KEY resolves to the entity key.
  const blank = check(sound({PROFILE_KEY: ""}), {profilesDefined: ["T_DIESEL"]});
  assert.equal(blank.some((f) => f.severity === "Error"), true,
    "the add-in records an Error here and the Console should show it");
  assert.equal(stopsThisSource(blank), false,
    "a blank PROFILE_KEY was reported as producing nothing, and it produces "
    + "everything — this is the mistake that called 13 of 17 sources broken");

  // These five really do produce nothing.
  assert.equal(stopsThisSource(check(sound({SOURCE_KEY: ""}))), true);
  assert.equal(stopsThisSource(check(sound({TARGET_ENTITY_KEY: ""}))), true);
  assert.equal(stopsThisSource(check(sound({TARGET_ENTITY_KEY: "T_TYPO"}))), true);
  assert.equal(stopsThisSource(check(sound({PROFILE_KEY: "P_NOWHERE"}))), true);
  assert.equal(stopsThisSource(check(sound({SOURCE_URI: ""}))), true);

  // And these do not.
  assert.equal(stopsThisSource(check(sound({DISPLAY_LABEL: ""}))), false);
  assert.equal(stopsThisSource(check(sound({SOURCE_REGION: "EGY"}))), false);
});

test("the suggested key follows the add-in's own convention", () => {
  assert.equal(suggestedKey({TARGET_ENTITY_KEY: "T_DIESEL", PROFILE_KEY: "P_X"}),
               "T_DIESEL_P_X");
  // DEFAULT is not part of a name — it IS the entity.
  assert.equal(suggestedKey({TARGET_ENTITY_KEY: "T_DIESEL", PROFILE_KEY: "DEFAULT"}),
               "T_DIESEL");
  assert.equal(suggestedKey({TARGET_ENTITY_KEY: "T_DIESEL", PROFILE_KEY: ""}),
               "T_DIESEL");
  assert.equal(suggestedKey({}), "");
});

test("every finding names the field it is about", () => {
  // The Console puts each of these beside its own input. A finding with no
  // field would render nowhere and be invisible.
  const found = check({SOURCE_KEY: "K", TARGET_ENTITY_KEY: "T_TYPO",
                       PROFILE_KEY: "", SOURCE_URI: "", SOURCE_REGION: "EGY"});
  assert.ok(found.length >= 4);
  for (const f of found) {
    assert.ok(f.field, `a finding has no field: ${f.detail?.slice(0, 40)}`);
    assert.ok(f.code, `a finding has no add-in error code: ${f.field}`);
  }
  assert.ok(fields(found).includes("SOURCE_URI"));
});

// ---------------------------------------------------------------------------
// A defect in the ADD-IN, found by a scanner pointed at this file.
//
// CodeQL flagged `lower.includes("docs.google.com")` as
// js/incomplete-url-substring-sanitization. The mirror is deliberate — the
// add-in matches exactly that way and this module's rule is to mirror rather
// than invent — but the consequence CodeQL named is real, and it belongs to the
// add-in: an address that merely MENTIONS docs.google.com passes every check it
// makes, and is then downloaded with no authentication.
//
// So the mirror was not deleted and was not silenced. It was SEPARATED. The
// add-in's substring test is `readsUriAsGoogleSheets` in the contract module,
// beside the other quirks it reproduces, and it decides nothing. What decides is
// the parsed host, here. The two tests below hold that separation in place: one
// proves the mirror still agrees with the add-in even where the add-in is wrong,
// the other proves the Console refuses anyway.
// ---------------------------------------------------------------------------

test("the mirror still agrees with the add-in, INCLUDING where it is wrong", () => {
  // If this ever goes false, the add-in has been repaired — and then the
  // impostor Error below becomes unreachable and should be reconsidered, not
  // deleted on the grounds that nothing hits it.
  assert.equal(
    readsUriAsGoogleSheets("https://attacker.example/?x=docs.google.com"), true,
    "the mirror no longer reproduces SourceUriValidator's substring match");
  assert.equal(readsUriAsGoogleSheets("https://DOCS.GOOGLE.COM/pub"), true,
    "the add-in matches case-insensitively and this no longer does");
  assert.equal(readsUriAsGoogleSheets(""), false);
  assert.equal(readsUriAsGoogleSheets(null), false);
});

test("and deciding by the mirror alone would accept the attack", () => {
  // Stated as an assertion rather than a comment, because this is the whole
  // reason the two live apart: agreeing with the add-in is NOT a safety verdict.
  const attack = "https://attacker.example/collect?x=docs.google.com&output=tsv";

  assert.equal(readsUriAsGoogleSheets(attack), true,
    "the add-in would call this a Google Sheet");
  assert.ok(checkSourceUri(attack).some((f) => f.severity === "Error"),
    "and the Console let it through, which means the host check has gone");
});

test("an address that only MENTIONS Google is refused, and says who serves it", () => {
  const found = checkSourceUri(
    "https://attacker.example/collect?x=docs.google.com&output=tsv");

  const impostor = found.filter((f) => /MENTIONS/.test(f.detail));
  assert.equal(impostor.length, 1);
  assert.equal(impostor[0].severity, "Error");
  assert.match(impostor[0].detail, /attacker\.example/,
    "the message does not name the host actually being talked to, which is the "
    + "one fact that settles it");
  assert.match(impostor[0].detail, /no authentication/);
});

test("a look-alike host is refused too", () => {
  // The other half of the same trick, and the one a reader is likeliest to miss.
  const found = checkSourceUri(
    "https://docs.google.com.attacker.example/pub?gid=1&output=tsv");
  assert.ok(found.some((f) => /MENTIONS/.test(f.detail)),
    "docs.google.com.attacker.example was accepted as Google's own host");
});

test("the real thing is not refused, on either Google host shape", () => {
  for (const uri of [PUBLISHED,
                     "https://spreadsheets.google.com/pub?gid=1&output=tsv"]) {
    assert.deepEqual(checkSourceUri(uri).filter((f) => /MENTIONS/.test(f.detail)),
      [], `${uri} was treated as an impostor`);
  }
});

test("the TSV rule still mirrors the add-in's substring match exactly", () => {
  // Deliberately NOT narrowed to the real host: the Console must ask for
  // output=tsv in precisely the cases the add-in does, or it is describing a
  // different program.
  const found = checkSourceUri("https://attacker.example/?x=docs.google.com");
  assert.ok(found.some((f) => /output=tsv/.test(f.fix)),
    "the TSV warning stopped firing for an address the add-in would still "
    + "treat as a Google Sheet");
});

test("a malformed address is refused rather than parsed by guesswork", () => {
  const found = checkSourceUri("https://exa mple.com/x.tsv");
  assert.equal(found.length, 1);
  assert.match(found[0].detail, /not a well-formed/);
});
