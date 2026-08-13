// One row of 4.DataMap, judged exactly as the add-in judges it.
//
// THE SHEET WHERE A WRONG VALUE BECOMES WRONG DATA. The add-in's own summary of
// its DataMap validation is that it is ADVISORY: findings become log lines and
// ETL alerts, and nothing filters a bad row out of the graph. The only things
// that actually stop a sync are four ingestion-time gates. So for SOURCE_TYPE,
// MATCH_MODE, TRANSFORM_CHAIN and PROCESS_CONFIG a wrong value reaches Excel as
// a warning plus wrong numbers, not as a refusal — which is the whole argument
// for a closed list at the moment of typing.
//
// Every rule below was read out of the C# with file:line
// (docs/reviews/mbiXaddin-config-contract-*.md).

import { readConfigBag, ERROR_CODE, CONSOLE_ONLY_CODE, SOURCE_TYPES, MATCH_MODES,
  CONTEXT_EXPRESSIONS, TRANSFORMS, PROCESS_CONFIG_KEYS, MAP_STRATEGIES,
  ROW_FILTER_OPERATORS, TRANSFORM_SEPARATOR, TRANSFORM_ARGUMENT_SEPARATOR }
  from "./addin-contract.js";

const finding = (severity, field, code, detail, fix = "") =>
  ({severity, field, code, detail, fix});

const text = (row, name) => String(row?.[name] ?? "").trim();
const same = (a, b) => a.toUpperCase() === b.toUpperCase();

/** Transforms that take arguments, and how many the code actually reads. */
const TRANSFORM_ARGUMENTS = {
  SUBSTRING: {least: 1, most: 2, what: "a 0-based start, and optionally a length"},
  JSON_EXTRACT: {least: 1, most: 1, what: "a key or a JSONPath"},
};

/**
 * What a source's PROFILE_KEY RESOLVES to — the value a DataMap row must carry.
 *
 * This is the join nobody can see from the sheet. `ResolveProfileKey` returns
 * the TARGET_ENTITY_KEY when the source's own PROFILE_KEY is blank or literally
 * "DEFAULT", and the custom key otherwise. So a DataMap row saying "DEFAULT" is
 * a dead row unless a table is literally named DEFAULT — and the add-in's own
 * doc comment offers "DEFAULT" as an example.
 */
export function resolvedProfiles(sources) {
  const keys = new Set();
  for (const source of sources || []) {
    const named = String(source?.PROFILE_KEY ?? "").trim();
    const entity = String(source?.TARGET_ENTITY_KEY ?? "").trim();
    keys.add(!named || same(named, "DEFAULT") ? entity : named);
  }
  keys.delete("");
  return [...keys].sort();
}

/** The attributes a profile may target: the columns of the table behind it. */
export function attributesFor(profile, sources, schemaRules) {
  const entities = new Set();
  for (const source of sources || []) {
    const named = String(source?.PROFILE_KEY ?? "").trim();
    const entity = String(source?.TARGET_ENTITY_KEY ?? "").trim();
    const resolved = !named || same(named, "DEFAULT") ? entity : named;
    if (same(resolved, profile)) entities.add(entity.toUpperCase());
  }
  // A profile named after a table with no source of its own still means that
  // table — which is the case while a wizard is building one.
  if (!entities.size) entities.add(profile.toUpperCase());
  return [...new Set((schemaRules || [])
    .filter((r) => entities.has(String(r?.ENTITY_KEY ?? "").trim().toUpperCase()))
    .map((r) => String(r?.ATTRIBUTE_KEY ?? "").trim())
    .filter(Boolean))].sort();
}

function checkTransformChain(chain, found) {
  if (!chain) return;                       // no chain: the raw value is stored
  for (const step of chain.split(TRANSFORM_SEPARATOR)) {
    const command = step.trim();
    if (!command) continue;                 // RemoveEmptyEntries, as the add-in does
    const [name, ...args] = command.split(TRANSFORM_ARGUMENT_SEPARATOR);
    const upper = name.trim().toUpperCase();

    if (!TRANSFORMS.includes(upper)) {
      found.push(finding("Error", "TRANSFORM_CHAIN", ERROR_CODE.transform,
        `"${name.trim()}" is not a transform the add-in has. It does NOT fail — `
        + "the value passes through UNCHANGED with a line in the log. So raw "
        + "text lands where a number was expected, and the type cast then "
        + "stores nothing at all.",
        `The ten it has: ${TRANSFORMS.join(", ")}.`));
      continue;
    }
    const wants = TRANSFORM_ARGUMENTS[upper];
    if (!wants && args.length) {
      found.push(finding("Warning", "TRANSFORM_CHAIN", ERROR_CODE.transform,
        `${upper} takes no arguments, and "${args.join(":")}" is ignored.`));
    } else if (wants && (args.length < wants.least || args.length > wants.most)) {
      found.push(finding("Error", "TRANSFORM_CHAIN", ERROR_CODE.transform,
        `${upper} needs ${wants.what}.`,
        `Write it as ${upper}:${"…"}.`));
    } else if (upper === "SUBSTRING"
               && args.some((a) => !/^-?\d+$/.test(a.trim()))) {
      // A malformed argument leaves the value unchanged rather than failing,
      // which is the same silent pass-through as an unknown command.
      found.push(finding("Error", "TRANSFORM_CHAIN", ERROR_CODE.transform,
        "SUBSTRING takes whole numbers. Anything else leaves the value "
        + "untouched, with no error and no sign that the step did nothing."));
    }
  }
}

function checkProcessConfig(raw, found) {
  if (!raw) return;
  if (!raw.startsWith("{")) {
    found.push(finding("Error", "PROCESS_CONFIG", ERROR_CODE.badFormat,
      "This must be a JSON object starting with a brace. Anything else — "
      + "including the retired $preset form — is logged and the WHOLE bag "
      + "falls back to its defaults."));
    return;
  }
  const {value: parsed, tolerated, unreadable} = readConfigBag(raw);
  if (unreadable) {
    found.push(finding("Error", "PROCESS_CONFIG", ERROR_CODE.badJson,
      "Nothing here can be read as an object, so every setting in it reverts "
      + "to its default."));
    return;
  }
  if (!parsed) return;
  if (tolerated) {
    found.push(finding("Info", "PROCESS_CONFIG", ERROR_CODE.badJson,
      "Not strict JSON — a trailing comma or a comment. The add-in's parser "
      + "accepts it."));
  }

  for (const key of Object.keys(parsed)) {
    // THE UNKNOWN-KEY CHECK IS EXACT-CASE in the add-in, while the value that
    // binds it is not — so "nullstrategy" is flagged as unknown AND still
    // applied. The Console reports the flag, because that is what the owner
    // will see in the log.
    if (!PROCESS_CONFIG_KEYS.includes(key)) {
      const meant = PROCESS_CONFIG_KEYS.find((k) => same(k, key));
      found.push(finding("Warning", "PROCESS_CONFIG", ERROR_CODE.unknownKey,
        meant
          ? `"${key}" is spelled with the wrong case. The add-in flags it as an `
            + `unknown key even though it still binds.`
          : `"${key}" is not a setting the add-in reads.`,
        meant ? `Write it as "${meant}".`
          : `Accepted: ${PROCESS_CONFIG_KEYS.join(", ")}.`));
    }
  }

  // THE CASE TRAP. Validation compares these case-insensitively; the runtime is
  // a C# string switch, which is not. So "usedefault" passes every check the
  // add-in makes and then silently behaves as Skip.
  for (const name of ["NullStrategy", "ErrorStrategy"]) {
    const value = parsed[name];
    if (value === undefined || value === null || value === "") continue;
    const asText = String(value);
    const exact = MAP_STRATEGIES.includes(asText);
    const loose = MAP_STRATEGIES.find((s) => same(s, asText));
    if (!loose) {
      found.push(finding("Error", "PROCESS_CONFIG", ERROR_CODE.badValue,
        `${name}="${asText}" is not a strategy.`,
        `Accepted: ${MAP_STRATEGIES.join(", ")}.`));
    } else if (!exact) {
      found.push(finding("Error", "PROCESS_CONFIG", ERROR_CODE.badValue,
        `${name}="${asText}" passes every check the add-in makes and then does `
        + `NOTHING: the runtime compares it exactly, so it falls through to `
        + `Skip. Nothing anywhere records that ${asText} was not understood.`,
        `Write it as "${loose}".`));
    }
  }

  if (parsed.NullStrategy === "UseDefault"
      && (parsed.DefaultValue === undefined || parsed.DefaultValue === null)) {
    found.push(finding("Warning", "PROCESS_CONFIG", ERROR_CODE.badValue,
      "UseDefault with no DefaultValue substitutes an empty value, which is "
      + "usually not what was meant."));
  }

  if ("AutoTrim" in parsed && typeof parsed.AutoTrim !== "boolean") {
    // A wrong JSON TYPE makes ToObject<T> throw and the ENTIRE bag reverts —
    // not just this key. That is worse than the key being wrong.
    found.push(finding("Error", "PROCESS_CONFIG", ERROR_CODE.badValue,
      `AutoTrim must be true or false, not "${parsed.AutoTrim}". A wrong type `
      + "here throws while the object is being read, and EVERY setting in the "
      + "bag reverts to its default — not just this one."));
  }

  const filter = parsed.RowFilter;
  if (filter) {
    const asText = String(filter);
    const cut = asText.indexOf(":");
    const operator = (cut > 0 ? asText.slice(0, cut) : asText).trim().toUpperCase();
    if (!ROW_FILTER_OPERATORS.includes(operator)) {
      found.push(finding("Error", "PROCESS_CONFIG", ERROR_CODE.badValue,
        `RowFilter "${asText}" starts with "${operator}", which is not an `
        + "operator. An unknown one KEEPS every row — the filter is silently "
        + "inert rather than refused.",
        `Accepted: ${ROW_FILTER_OPERATORS.join(", ")}.`));
    } else if (!["EMPTY", "NOT_EMPTY"].includes(operator) && cut < 1) {
      found.push(finding("Error", "PROCESS_CONFIG", ERROR_CODE.badValue,
        `${operator} needs a value after a colon, as in "${operator}:something". `
        + "Without one it compares against nothing."));
    }
  }
}

/**
 * One DataMap row, against the rest of the workbook.
 *
 * `others` is every OTHER row of 4.DataMap — the same convention as the three
 * sheets before it. `sources` and `schemaRules` are needed for the join that
 * cannot be seen from this sheet at all: which table a profile actually feeds.
 */
export function checkDataMapRow(row, others = [], sources = [], schemaRules = []) {
  const found = [];
  const profile = text(row, "PROFILE_KEY");
  const target = text(row, "TARGET_ATTRIBUTE_KEY");

  // 1 and 2 — the add-in's two Critical fields. It stops at either.
  if (!profile) {
    return [finding("Critical", "PROFILE_KEY", ERROR_CODE.required,
      "Every mapping must belong to a profile. With none, nothing can ever "
      + "look this row up.")];
  }
  if (!target) {
    return [finding("Critical", "TARGET_ATTRIBUTE_KEY", ERROR_CODE.required,
      "No column to write into, so this mapping has nowhere to put a value.")];
  }

  // 3 — the trap in the add-in's own documentation.
  if (same(profile, "DEFAULT")) {
    found.push(finding("Error", "PROFILE_KEY", ERROR_CODE.reference,
      "A profile literally named DEFAULT is a DEAD ROW. A source with a blank "
      + "or DEFAULT profile resolves to its TABLE's key, so the mapping has to "
      + "carry the table name here — never the word DEFAULT, which the add-in's "
      + "own comment offers as an example.",
      "Use the table's key."));
  } else if (sources.length) {
    const live = resolvedProfiles(sources);
    if (!live.some((p) => same(p, profile))) {
      found.push(finding("Warning", "PROFILE_KEY", ERROR_CODE.orphanMapping,
        `No source resolves to "${profile}", so these mappings never run. They `
        + "are not an error and nothing reports them at sync time — they simply "
        + "sit there."));
    }
  }

  // 4 — the column it writes into. A name the schema does not have is dropped
  // with a yellow warning and the column is never written.
  if (/\s/.test(target)) {
    found.push(finding("Warning", "TARGET_ATTRIBUTE_KEY", ERROR_CODE.badFormat,
      "Internal spaces are silently replaced with underscores before the "
      + "lookup. It usually works, and it means the name here is not the name "
      + "being matched.",
      "Type it with underscores."));
  }
  if (schemaRules.length) {
    const allowed = attributesFor(profile, sources, schemaRules);
    const cleaned = target.replace(/\s+/g, "_");
    if (allowed.length && !allowed.some((a) => same(a, cleaned))) {
      found.push(finding("Error", "TARGET_ATTRIBUTE_KEY", ERROR_CODE.orphanMapping,
        `No column called "${cleaned}" is defined for this profile's table. The `
        + "mapping is dropped as an orphan and its data is lost — with a "
        + "warning, and the sync carries on.",
        `Defined: ${allowed.slice(0, 12).join(", ")}`
        + `${allowed.length > 12 ? ", …" : ""}.`));
    }
  }

  // 5 — two rows writing the same column. Not enforced anywhere: both survive
  // unless the expression is identical too, both run, and the LAST in sheet
  // order wins — while either one's RowFilter can still drop the row.
  const twin = others.find((other) => same(text(other, "PROFILE_KEY"), profile)
    && same(text(other, "TARGET_ATTRIBUTE_KEY"), target));
  if (twin) {
    found.push(finding("Error", "TARGET_ATTRIBUTE_KEY",
      CONSOLE_ONLY_CODE.silentOverride,
      `"${target}" is mapped more than once in ${profile}. Both rows run and the `
      + "LAST one on the sheet wins, so which value is stored depends on row "
      + "order — and either row's filter can still drop the whole row.",
      "Delete the mapping that is not wanted."));
  }

  // 6 — where the value comes from.
  const sourceType = text(row, "SOURCE_TYPE");
  const kind = SOURCE_TYPES.find((t) => same(t, sourceType)) || "";
  if (sourceType && !kind) {
    found.push(finding("Error", "SOURCE_TYPE", ERROR_CODE.badValue,
      `"${sourceType}" is not a source type.`,
      `Accepted: ${SOURCE_TYPES.join(", ")}.`));
  }
  const effective = kind || "Header";        // a blank cell means Header
  const expression = text(row, "SOURCE_EXPRESSION");

  if (effective === "Formula") {
    found.push(finding("Error", "SOURCE_TYPE", CONSOLE_ONLY_CODE.notApplied,
      "Formula is NOT IMPLEMENTED. It has no branch in the code, so it falls to "
      + "the default and returns null for EVERY row — and if this column is a "
      + "key or is required, every row is then dropped.",
      "Use Header, Index, Context or Constant."));
  }
  if (effective === "Index") {
    if (!/^\d+$/.test(expression)) {
      found.push(finding("Error", "SOURCE_EXPRESSION", ERROR_CODE.badValue,
        `Index reads a COLUMN POSITION, counted from 0 — not a row number, `
        + "whatever the add-in's own documentation says. "
        + `"${expression || "(empty)"}" is not one.`,
        "Type the column's position, starting at 0."));
    }
  } else if (effective === "Context") {
    if (!CONTEXT_EXPRESSIONS.some((t) => same(t, expression))) {
      found.push(finding("Error", "SOURCE_EXPRESSION", ERROR_CODE.badValue,
        `Context accepts exactly four tokens, and "${expression || "(empty)"}" `
        + "is not one of them — it writes null into every row. The add-in's own "
        + "comments advertise CurrentCountry and CurrentUser, and both are "
        + "documentation only.",
        `The four: ${CONTEXT_EXPRESSIONS.join(", ")}.`));
    }
  } else if (effective === "Header" && !expression) {
    found.push(finding("Error", "SOURCE_EXPRESSION", ERROR_CODE.required,
      "Header needs the column heading to look for in the file. With none, "
      + "nothing matches and this column is never filled."));
  } else if (effective === "Constant" && !expression) {
    found.push(finding("Warning", "SOURCE_EXPRESSION", ERROR_CODE.required,
      "A constant with no value writes an empty string into every row."));
  }

  // 7 — how the heading is matched, which only matters for one source type.
  const matchMode = text(row, "MATCH_MODE");
  const mode = MATCH_MODES.find((m) => same(m, matchMode)) || "";
  if (matchMode && !mode) {
    found.push(finding("Error", "MATCH_MODE", ERROR_CODE.badValue,
      `"${matchMode}" is not a match mode.`,
      `Accepted: ${MATCH_MODES.join(", ")}.`));
  }
  if (mode && !same(mode, "Exact") && effective !== "Header") {
    found.push(finding("Warning", "MATCH_MODE", ERROR_CODE.badValue,
      `${mode} is read only when the source type is Header. Here it does `
      + "nothing at all.",
      "Leave it blank, or set it to Exact."));
  }
  if (same(mode, "Regex") && effective === "Header" && expression) {
    try {
      new RegExp(expression);
    } catch {
      found.push(finding("Error", "SOURCE_EXPRESSION", ERROR_CODE.badValue,
        "This pattern does not compile. The add-in does NOT fail on it — it "
        + "logs the error and then matches nothing, which surfaces later as "
        + "\"header not found\" and sends you looking at the file instead."));
    }
  }
  if (same(mode, "Fuzzy") && effective === "Header") {
    found.push(finding("Warning", "MATCH_MODE", ERROR_CODE.badValue,
      "Fuzzy accepts any heading within two edits, and the FIRST one that "
      + "close wins. Two similar headings in one file bind the wrong column "
      + "with no warning."));
  }

  checkTransformChain(text(row, "TRANSFORM_CHAIN"), found);
  checkProcessConfig(text(row, "PROCESS_CONFIG"), found);
  return found;
}

/**
 * What a profile is MISSING, which no single row can answer.
 *
 * Two of the four gates that actually stop a sync live here: a profile with no
 * mappings at all, and a required column whose mapping never resolved.
 */
export function checkProfileCoverage(profile, maps, sources, schemaRules) {
  const found = [];
  const mine = (maps || []).filter(
    (m) => same(String(m?.PROFILE_KEY ?? "").trim(), profile));

  if (!mine.length) {
    return [finding("Critical", "PROFILE_KEY", ERROR_CODE.orphanMapping,
      `Nothing maps ${profile}. Every source using it FAILS OUTRIGHT — this is `
      + "one of the four faults that stop a sync rather than warn about it.",
      "Map at least the key column.")];
  }

  const mapped = new Set(mine.map(
    (m) => String(m?.TARGET_ATTRIBUTE_KEY ?? "").trim().replace(/\s+/g, "_")
      .toUpperCase()));
  const entities = new Set();
  for (const source of sources || []) {
    const named = String(source?.PROFILE_KEY ?? "").trim();
    const entity = String(source?.TARGET_ENTITY_KEY ?? "").trim();
    if (same(!named || same(named, "DEFAULT") ? entity : named, profile)) {
      entities.add(entity.toUpperCase());
    }
  }
  if (!entities.size) entities.add(profile.toUpperCase());

  for (const rule of schemaRules || []) {
    if (!entities.has(String(rule?.ENTITY_KEY ?? "").trim().toUpperCase())) continue;
    const attribute = String(rule?.ATTRIBUTE_KEY ?? "").trim();
    if (!attribute || mapped.has(attribute.toUpperCase())) continue;
    const isKey = String(rule?.IS_PK ?? "").trim().toLowerCase();
    const required = String(rule?.IS_MANDATORY ?? "").trim().toLowerCase();
    const truthy = (v) => ["1", "true", "yes", "y", "on", "نعم", "صح", "صحيح"]
      .includes(v);
    if (truthy(isKey)) {
      found.push(finding("Critical", "TARGET_ATTRIBUTE_KEY",
        ERROR_CODE.mandatoryUnmapped,
        `The key column ${attribute} has no mapping. Under MergeUpsert the sync `
        + "is refused before anything is written.",
        `Map ${attribute}.`));
    } else if (truthy(required)) {
      found.push(finding("Critical", "TARGET_ATTRIBUTE_KEY",
        ERROR_CODE.mandatoryUnmapped,
        `${attribute} is required and has no mapping, so the whole source is `
        + "rejected before any write.",
        `Map ${attribute}.`));
    }
  }
  return found;
}
