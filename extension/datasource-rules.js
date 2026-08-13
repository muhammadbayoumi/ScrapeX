// One row of 3.DataSource, judged exactly as the add-in judges it.
//
// EVERY RULE HERE IS THE ADD-IN'S, NOT MINE. `DataSourceEntity.Validate()` has
// eight; `SourceUriValidator` has six more for the address. Both were read out
// of the C# with file:line (docs/reviews/mbiXaddin-config-contract-*.md). A
// rule invented here would be a Console refusing something the add-in accepts,
// and that teaches an owner to work around the Console rather than with it.
//
// SEVERITY IS THE ADD-IN'S TOO. Its four levels are Info, Warning, Error and
// Critical, and only Error and above block a sync. Critical additionally stops
// the rest of that row being checked — so the Console stops with it, or it
// would print a cascade of complaints about a row the add-in never reaches.

import { readBoolean, BOOLEAN_DEFAULTS, ERROR_CODE } from "./addin-contract.js";

/** Severities in the order the add-in ranks them. */
const RANK = {Info: 0, Warning: 1, Error: 2, Critical: 3};

const finding = (severity, field, code, detail, fix = "") =>
  ({severity, field, code, detail, fix});

/**
 * The address rules, which are the ones an owner gets wrong most often.
 *
 * `SourceUriValidator`'s own file header calls rule 4 "the single most common
 * data-entry mistake": a Google Sheets URL with no `output=tsv`. The add-in
 * then downloads a WEB PAGE, sniffs the first 256 characters, sees `<!DOCTYPE`
 * and reports a parse failure — which reads as a problem with the data rather
 * than with the address, and sends the owner looking in the wrong place.
 */
export function checkSourceUri(uri) {
  const value = String(uri ?? "").trim();
  const found = [];

  if (!value) {
    return [finding("Critical", "SOURCE_URI", ERROR_CODE.required,
      "There is no address, so there is nothing to load.",
      "In the source spreadsheet: File → Share → Publish to web → select the "
      + "sheet → TSV format.")];
  }

  const lower = value.toLowerCase();
  const isHttp = lower.startsWith("http://") || lower.startsWith("https://");
  // The add-in accepts a local path too: a leading slash, a backslash anywhere,
  // or a drive letter followed by a colon.
  const isLocal = value.startsWith("/") || value.includes("\\")
    || (value.length > 1 && value[1] === ":");

  if (!isHttp && !isLocal) {
    // Stops here in the add-in as well — every later rule assumes one of the
    // two shapes.
    return [finding("Error", "SOURCE_URI", ERROR_CODE.badValue,
      "This is neither a web address nor a file path. FTP, relative paths and "
      + "bare filenames are not supported.")];
  }

  if (isHttp) {
    const authority = value.slice(value.indexOf("//") + 2).split("/")[0];
    if (!authority.includes(".")) {
      found.push(finding("Warning", "SOURCE_URI", ERROR_CODE.badValue,
        `"${authority}" has no dot in it, so it is probably not a real host.`));
    }
  }

  // Case-insensitive substring, exactly as the add-in matches.
  if (lower.includes("docs.google.com")) {
    if (!lower.includes("output=tsv") && !lower.includes("format=tsv")) {
      found.push(finding("Error", "SOURCE_URI", ERROR_CODE.badValue,
        "A Google Sheets address without a TSV format serves a WEB PAGE. The "
        + "add-in downloads it, sees markup where rows should be, and reports a "
        + "parse failure — which reads as a problem with the data rather than "
        + "with this address.",
        "Add output=tsv to the end of the address."));
    }
    if (!lower.includes("gid=")) {
      found.push(finding("Warning", "SOURCE_URI", ERROR_CODE.badValue,
        "No gid, so this always reads the FIRST tab of that spreadsheet — "
        + "whichever one that happens to be today.",
        "Add gid=… naming the tab you mean."));
    }
  } else if (isLocal
             && !/\.(csv|tsv|txt)/i.test(value)) {
    found.push(finding("Warning", "SOURCE_URI", ERROR_CODE.badValue,
      "A local path with no .csv, .tsv or .txt in it."));
  }

  return found;
}

/**
 * One DataSource row, against the whole workbook — because half its rules are
 * about what other sheets contain.
 *
 * `others` is every OTHER row of 3.DataSource, so uniqueness can be judged
 * without the row colliding with itself while it is being edited.
 */
export function checkDataSourceRow(row, {entities = [], activeEntities = null,
                                         profilesDefined = [], others = []} = {}) {
  const found = [];
  const value = (name) => String(row?.[name] ?? "").trim();

  // 1 — SOURCE_KEY. Critical, and the add-in ABANDONS the row here: it keys
  // _SYS_SYNC_STATE and per-row provenance, so without it nothing downstream
  // can be attributed at all.
  const key = value("SOURCE_KEY");
  if (!key) {
    return [finding("Critical", "SOURCE_KEY", ERROR_CODE.required,
      "Without a key the add-in stops reading this row entirely — nothing else "
      + "about it is even checked.",
      "The convention is {TARGET_ENTITY_KEY}_{PROFILE_KEY}.")];
  }

  // A duplicate is worse than it sounds: because SOURCE_KEY keys the sync state,
  // removing one source can delete another's rows.
  const twin = others.find(
    (o) => String(o?.SOURCE_KEY ?? "").trim().toLowerCase() === key.toLowerCase());
  if (twin) {
    found.push(finding("Error", "SOURCE_KEY", ERROR_CODE.duplicate,
      `"${key}" is already used${twin._row ? ` on row ${twin._row}` : ""}. Keys `
      + "identify a source's own stored state, so a duplicate can make removing "
      + "one source delete another's rows."));
  }

  // 2 — TARGET_ENTITY_KEY. Critical when blank; and when it names nothing the
  // add-in does not fail, it SILENTLY DROPS the source from the graph.
  const entity = value("TARGET_ENTITY_KEY");
  if (!entity) {
    found.push(finding("Critical", "TARGET_ENTITY_KEY", ERROR_CODE.required,
      "This source loads into no table."));
  } else {
    const known = entities.some((e) => e.toLowerCase() === entity.toLowerCase());
    if (!known) {
      found.push(finding("Error", "TARGET_ENTITY_KEY", ERROR_CODE.reference,
        `No table is called "${entity}". The add-in drops a source like this `
        + "from the graph with a warning nobody reads — it never syncs, and "
        + "nothing says why."));
    } else if (activeEntities
               && !activeEntities.some((e) => e.toLowerCase() === entity.toLowerCase())) {
      // The reference resolves and the table is switched off, so this source
      // still never runs. A different fault with the same symptom.
      found.push(finding("Warning", "TARGET_ENTITY_KEY", ERROR_CODE.reference,
        `"${entity}" exists but is not active, so this source never syncs. `
        + "The add-in filters inactive tables out before it builds anything."));
    }
  }

  // 3 — PROFILE_KEY. Blank WORKS — it resolves to the entity key — and the
  // add-in records an Error about it anyway. Both halves are true and the
  // Console has to say both, or the owner "fixes" something that was working
  // or ignores a message that is real.
  const profile = value("PROFILE_KEY");
  const resolved = (!profile || profile.toUpperCase() === "DEFAULT") ? entity : profile;
  if (!profile) {
    found.push(finding("Error", "PROFILE_KEY", ERROR_CODE.required,
      `Blank, which the add-in resolves to "${entity || "the table's key"}" and `
      + "records an Error about at the same time. It works; it is noisy.",
      entity ? `Write ${entity} here to say plainly what it already does.` : ""));
  }
  if (resolved && profilesDefined.length
      && !profilesDefined.some((p) => p.toLowerCase() === resolved.toLowerCase())) {
    found.push(finding("Error", "PROFILE_KEY", ERROR_CODE.orphanMapping,
      `Nothing in 4.DataMap defines "${resolved}", so this source FAILS to `
      + "ingest — not silently: the table ends up empty."));
  }

  // 4 — the address.
  found.push(...checkSourceUri(row?.SOURCE_URI));

  // 5 — SOURCE_REGION. The consequence is out of all proportion to the typo.
  const region = value("SOURCE_REGION");
  if (region && region.toUpperCase() !== "GLOBAL" && !/^[A-Za-z]{2}$/.test(region)) {
    found.push(finding("Warning", "SOURCE_REGION", ERROR_CODE.badValue,
      `"${region}" is neither GLOBAL nor a two-letter code, and an unrecognised `
      + "region BLOCKS EVERY USER from syncing this source.",
      "Use GLOBAL, or a two-letter country code such as SA or EG."));
  }

  // 6 — DISPLAY_LABEL.
  if (!value("DISPLAY_LABEL")) {
    found.push(finding("Warning", "DISPLAY_LABEL", ERROR_CODE.required,
      "No label, so this source appears under its key wherever it is named."));
  }

  // 7 — switched off. Not a fault; said because a table that is empty on
  // purpose looks exactly like a table that is empty by accident.
  const active = readBoolean(row?.IS_ACTIVE, BOOLEAN_DEFAULTS["3.DataSource"].IS_ACTIVE);
  if (!active) {
    found.push(finding("Info", "IS_ACTIVE", ERROR_CODE.badValue,
      "Switched off — the add-in skips this source entirely, and its table "
      + "stays as it was."));
  }

  // 8 — the JSON bag.
  const bag = value("CONTEXT_PROPS");
  if (bag) {
    try {
      const parsed = JSON.parse(bag);
      if (parsed === null || typeof parsed !== "object" || Array.isArray(parsed)) {
        found.push(finding("Error", "CONTEXT_PROPS", ERROR_CODE.badJson,
          "This is valid JSON but not an object, so no setting can be read out "
          + "of it."));
      }
    } catch {
      found.push(finding("Error", "CONTEXT_PROPS", ERROR_CODE.badJson,
        "Not valid JSON, so every setting inside it is ignored."));
    }
  }

  found.sort((a, b) => RANK[b.severity] - RANK[a.severity]);
  return found;
}

/**
 * Does this source produce NOTHING — and that is a different question from the
 * severity beside each finding.
 *
 * MY FIRST VERSION ASKED "IS ANYTHING HERE AN ERROR", AND IT WAS WRONG. Run
 * over the owner's real workbook it declared 13 of 17 sources blocked, all of
 * which sync every day. The reason is that `SyncManager` does not gate on a
 * DataSource ROW at all: it gates on `ValidateContext`, the per-ENTITY report,
 * and that report lists "a source whose PROFILE_KEY has no mappings" among the
 * warnings that explicitly do NOT block. A row's own Error is recorded and
 * alerted; the sync goes on.
 *
 * So severity answers "what does the add-in write in its log", and this answers
 * "does anything come out of this source". Conflating them is how a Console
 * reports thirteen catastrophes a day until nobody opens it.
 *
 * These five genuinely produce nothing:
 *   - no SOURCE_KEY      the row is abandoned before anything else is read
 *   - no TARGET_ENTITY_KEY, or one that names nothing — dropped from the graph
 *   - a profile with no mappings — IngestionResult.Fail, per source
 *   - no address, or one the downloader refuses outright
 *   - switched off — which is not a fault, and is reported separately
 */
export function stopsThisSource(found) {
  return found.some((f) =>
    f.severity === "Critical"
    || (f.field === "TARGET_ENTITY_KEY" && f.code === ERROR_CODE.reference
        && /drops a source/.test(f.detail))
    || (f.field === "PROFILE_KEY" && f.code === ERROR_CODE.orphanMapping)
    || (f.field === "SOURCE_URI" && RANK[f.severity] >= RANK.Error));
}

/** Switched off on purpose — empty, and not a fault. Asked separately. */
export function switchedOff(found) {
  return found.some((f) => f.field === "IS_ACTIVE" && f.severity === "Info");
}

/** The suggested key, by the add-in's own stated convention. */
export function suggestedKey(row) {
  const entity = String(row?.TARGET_ENTITY_KEY ?? "").trim();
  const profile = String(row?.PROFILE_KEY ?? "").trim();
  if (!entity) return "";
  return profile && profile.toUpperCase() !== "DEFAULT"
    ? `${entity}_${profile}` : entity;
}
