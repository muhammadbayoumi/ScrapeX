// One row of 6.RibbonControls, judged exactly as the add-in judges it.
//
// THIS SHEET DECIDES WHAT THE OWNER'S USERS CAN CLICK, and almost nothing on it
// fails loudly. `RibbonControlEntity.Validate()` has one Critical for a blank
// ITEM_KEY, one for a self-parent, and Warnings for the rest; everything else
// here resolves to a default, renders nowhere, or waits to fail on a click.
//
// THE DEFAULT THAT IS NOT A VALUE. A blank CONTROL_KEY becomes "mnuDynamic"
// (RibbonControlService.cs:513) — and NO control of that name exists in the
// shipped ribbon. The row is then never selected by any FillMenu or BindButton
// call, so it renders NOWHERE, and nothing anywhere reports it. That is the
// single most consequential blank on this sheet and it looks like every other
// harmless empty cell.
//
// A BAD ACTION_CLASS IS THE BUTTON THAT THROWS WHEN PRESSED. It builds fine and
// renders normally; the failure arrives only on the click, as a modal titled
// "Unknown Action" (ActionRouter.cs:147-167). The Console exists to move that
// discovery from the user's morning to the author's screen.

import { readBoolean, BOOLEAN_DEFAULTS, ERROR_CODE, CONSOLE_ONLY_CODE,
  ACTION_CLASSES, CLICKABLE_ACTIONS, MENU_ACTIONS, MENU_LAYOUTS,
  RIBBON_CONTROL_KEYS, RIBBON_CONTROL_KEY_DEFAULT }
  from "./addin-contract.js";

/** Severities in the order the add-in ranks them. */
const RANK = {Info: 0, Warning: 1, Error: 2, Critical: 3};

const finding = (severity, field, code, detail, fix = "") =>
  ({severity, field, code, detail, fix});

const text = (row, column) => String(row?.[column] ?? "").trim();

/**
 * Spellings the add-in's own doc comments still offer and the code REFUSES.
 *
 * They were removed deliberately (RibbonControlEntity.cs:159-171, :632 are the
 * stale comments), so an author copying from the add-in's own documentation
 * writes a button that renders and then throws a dialog when pressed. The
 * Console must name them rather than say "not a valid value", because the
 * author has a source in front of them that says otherwise.
 */
const RETIRED_ACTION_CLASSES = {
  ExportEntity: "Export", ExportService: "Export",
  DownloadService: "Download", OpenView: "ViewList",
};

/** The effective CONTROL_KEY, applying the add-in's own blank default. */
export function effectiveControlKey(row) {
  const key = text(row, "CONTROL_KEY");
  return key || RIBBON_CONTROL_KEY_DEFAULT;
}

/** The effective ACTION_CLASS. Blank means Export, applied in two places. */
export function effectiveActionClass(row) {
  return text(row, "ACTION_CLASS") || "Export";
}

/** Does this class build a menu instead of being routed on a click? */
export function buildsAMenu(actionClass) {
  return MENU_ACTIONS.some(
    (m) => m.toLowerCase() === String(actionClass ?? "").toLowerCase());
}

/**
 * ACTION_TAG, split as `EntityKeyFromTag` / `ViewKeyFromTag` split it — one
 * pipe at most, the leading segment always the ENTITY_KEY
 * (RibbonControlEntity.cs:369-394).
 */
export function splitActionTag(raw) {
  const value = String(raw ?? "").trim();
  const pipe = value.indexOf("|");
  if (pipe < 0) return {entity: value, view: ""};
  return {entity: value.slice(0, pipe).trim(), view: value.slice(pipe + 1).trim()};
}

/**
 * One 6.RibbonControls row.
 *
 * `others` is every OTHER row, because half of what can go wrong here is about
 * a row's relationship to its siblings: a PARENT_KEY resolves only among rows
 * of the SAME CONTROL_KEY that survived the region filter, so a parent one
 * control away orphans the child in silence.
 */
export function checkRibbonControlRow(row, others = [], views = [],
                                      definitions = []) {
  const found = [];
  const itemKey = text(row, "ITEM_KEY");

  // ---- the add-in's Critical, and it stops the row -------------------------
  if (!itemKey) {
    return [finding("Critical", "ITEM_KEY", ERROR_CODE.required,
      "A control with no key is rejected whole (RibbonControlEntity.cs:420-428) "
      + "and the SQLite read path drops it even earlier, before the entity is "
      + "built at all.",
      "Give it a key; other rows point at it by this name.")];
  }

  // ---- CONTROL_KEY: the blank that renders nowhere -------------------------
  const controlRaw = text(row, "CONTROL_KEY");
  const controlKey = effectiveControlKey(row);
  if (!controlRaw) {
    found.push(finding("Error", "CONTROL_KEY", CONSOLE_ONLY_CODE.silentDrop,
      `A blank cell becomes "${RIBBON_CONTROL_KEY_DEFAULT}", and no control of `
      + "that name exists in the shipped ribbon — so this row renders NOWHERE. "
      + "Nothing reports it: the row is simply never selected by any menu or "
      + "button, and the control it was meant for shows \"No items "
      + "configured.\"",
      "Name the menu or button this item belongs to."));
  } else if (!RIBBON_CONTROL_KEYS.some(
      (k) => k.toLowerCase() === controlKey.toLowerCase())) {
    found.push(finding("Error", "CONTROL_KEY", CONSOLE_ONLY_CODE.silentDrop,
      `"${controlKey}" is not a control wired to the sheet. Twenty-one menus `
      + "and two buttons are, and mnuExport is NOT among them — it is built in "
      + "code, not from this sheet. An unmatched key produces no error at all; "
      + "the row just never renders.",
      `Use one of: ${RIBBON_CONTROL_KEYS.join(", ")}`));
  }

  // ---- ACTION_CLASS: eight values, and four of them build menus ------------
  const actionRaw = text(row, "ACTION_CLASS");
  const actionClass = effectiveActionClass(row);
  const retired = Object.keys(RETIRED_ACTION_CLASSES).find(
    (name) => name.toLowerCase() === actionClass.toLowerCase());
  const known = ACTION_CLASSES.find(
    (name) => name.toLowerCase() === actionClass.toLowerCase());

  if (retired) {
    found.push(finding("Error", "ACTION_CLASS", ERROR_CODE.badValue,
      `"${retired}" was removed. The add-in's own doc comments still offer it, `
      + "which is why it keeps being typed — but the router does not know it, "
      + "so the button renders normally and shows an \"Unknown Action\" dialog "
      + "when someone presses it.",
      `Use "${RETIRED_ACTION_CLASSES[retired]}".`));
  } else if (!known) {
    found.push(finding("Error", "ACTION_CLASS", ERROR_CODE.badValue,
      `"${actionClass}" resolves to nothing. Nothing fails while the ribbon is `
      + "built — the button appears, and the failure is a modal titled "
      + "\"Unknown Action\" the first time a user presses it.",
      `Four run on click (${CLICKABLE_ACTIONS.join(", ")}) and four build a `
      + `menu (${MENU_ACTIONS.join(", ")}).`));
  } else if (known !== actionClass && actionRaw) {
    found.push(finding("Info", "ACTION_CLASS", ERROR_CODE.badValue,
      `Matched case-insensitively, so "${actionClass}" works — the add-in's own `
      + `spelling is "${known}".`,
      `Write "${known}".`));
  }

  // ---- ACTION_TAG: required off Menu, and forbidden on it ------------------
  const tagRaw = text(row, "ACTION_TAG");
  const isMenu = known && known.toLowerCase() === "menu";
  if (isMenu && tagRaw) {
    found.push(finding("Warning", "ACTION_TAG", ERROR_CODE.badFormat,
      "A Menu container carries no tag — this value is ignored.",
      "Clear it; the children below carry the actions."));
  } else if (!isMenu && !tagRaw) {
    found.push(finding("Error", "ACTION_TAG", ERROR_CODE.required,
      "Every class but Menu needs a tag (RibbonControlEntity.cs:479-485). "
      + "Without one the click reports \"No action configured for this "
      + "button.\"",
      "Name the ENTITY_KEY this acts on."));
  } else if (tagRaw) {
    const {entity, view} = splitActionTag(tagRaw);
    if ((tagRaw.match(/\|/g) || []).length > 1) {
      found.push(finding("Warning", "ACTION_TAG", ERROR_CODE.badFormat,
        "One pipe at most. Everything after the first is read as the view key, "
        + "so a second pipe lands inside it.",
        "Write ENTITY_KEY or ENTITY_KEY|VIEW_KEY."));
    }
    const entities = (definitions || [])
      .map((d) => text(d, "ENTITY_KEY")).filter(Boolean);
    if (entity && entities.length
        && !entities.some((k) => k.toLowerCase() === entity.toLowerCase())) {
      found.push(finding("Error", "ACTION_TAG", ERROR_CODE.reference,
        `No table is defined with the key "${entity}". On an Export that `
        + "surfaces as an \"Export Failed\" dialog; on Library, ExportTree or "
        + "ViewList it is a disabled item reading \"Not configured — see the "
        + "log\".",
        "Point it at a key on 1.TableDefinition."));
    }
    // The dangerous half: a view key that misses is NOT an error anywhere.
    if (view && (views || []).length) {
      const match = (views || []).find(
        (v) => text(v, "VIEW_KEY").toLowerCase() === view.toLowerCase());
      if (!match) {
        found.push(finding("Error", "ACTION_TAG", CONSOLE_ONLY_CODE.silentDrop,
          `No view is defined with the key "${view}". GetExportView returns `
          + "null and the engine then exports the FULL table — every row, "
          + "every column, no aliases — instead of the filtered view. Nothing "
          + "reports it; the export simply contains more than it should.",
          "Correct it to a VIEW_KEY on 5.ExportViews."));
      } else if (text(match, "ENTITY_KEY").toLowerCase()
                 !== entity.toLowerCase()) {
        found.push(finding("Warning", "ACTION_TAG", ERROR_CODE.reference,
          `"${view}" belongs to ${text(match, "ENTITY_KEY")}, not ${entity}. `
          + "The view is found by key alone, so the mismatch is not refused — "
          + "it is applied to the wrong table.",
          "Use a view of this entity."));
      }
    }
  }

  // ---- REGION -------------------------------------------------------------
  const regionRaw = text(row, "REGION");
  if (!regionRaw) {
    found.push(finding("Warning", "REGION", ERROR_CODE.required,
      "A blank region means GLOBAL — visible everywhere. That is a real "
      + "choice and the add-in warns about it rather than assuming it silently.",
      "Write GLOBAL to say so, or list the 2-letter codes."));
  } else if (regionRaw.toUpperCase() !== "GLOBAL") {
    for (const token of regionRaw.split(",").map((t) => t.trim()).filter(Boolean)) {
      if (!/^[A-Za-z]{2}$/.test(token)) {
        found.push(finding("Warning", "REGION", ERROR_CODE.badFormat,
          `"${token}" is not a 2-letter ISO code, so it matches no region — and `
          + "it POLLUTES the region dropdown, whose vocabulary is built at "
          + "runtime from the tokens found on this sheet.",
          "Use codes like EG or SA, separated by commas."));
      }
    }
  }

  // ---- PARENT_KEY: resolved only among siblings of the SAME control --------
  const parentKey = text(row, "PARENT_KEY");
  if (parentKey) {
    if (parentKey.toLowerCase() === itemKey.toLowerCase()) {
      found.push(finding("Critical", "PARENT_KEY", ERROR_CODE.circular,
        "A row cannot be its own parent (RibbonControlEntity.cs:496-501).",
        "Clear it to make this a top-level item."));
    } else {
      const parent = (others || []).find(
        (o) => text(o, "ITEM_KEY").toLowerCase() === parentKey.toLowerCase());
      if (!parent) {
        found.push(finding("Error", "PARENT_KEY", ERROR_CODE.reference,
          `No row has ITEM_KEY "${parentKey}", so this item is never `
          + "enumerated by anything and renders nowhere.",
          "Point it at a row on this sheet, or clear it."));
      } else {
        if (effectiveControlKey(parent).toLowerCase() !== controlKey.toLowerCase()) {
          found.push(finding("Error", "PARENT_KEY", CONSOLE_ONLY_CODE.silentDrop,
            `The parent belongs to "${effectiveControlKey(parent)}" and this `
            + `row to "${controlKey}". Children are gathered only among rows of `
            + "the SAME control, so this one is orphaned — it renders nowhere "
            + "and nothing says why.",
            "Give both rows the same CONTROL_KEY."));
        }
        if (!buildsAMenu(effectiveActionClass(parent))) {
          found.push(finding("Warning", "PARENT_KEY", CONSOLE_ONLY_CODE.silentDrop,
            `"${parentKey}" is a ${effectiveActionClass(parent)} row, not a `
            + "container. Children of a leaf are never enumerated, so this "
            + "item does not appear under it.",
            "Parent it to a row whose ACTION_CLASS is Menu."));
        }
        // A→B→A is NOT detected by the add-in; the recursive builder loops.
        const cycle = walkToRoot(parent, others, itemKey);
        if (cycle) {
          found.push(finding("Error", "PARENT_KEY", ERROR_CODE.circular,
            `This item is its own ancestor (${cycle}). Only a row parented to `
            + "ITSELF is Critical in the add-in; a longer ring passes every "
            + "check it makes and the menu builder recurses on it.",
            "Break the ring."));
        }
      }
    }
  }

  // ---- ORDER --------------------------------------------------------------
  const orderRaw = text(row, "ORDER");
  if (orderRaw && !/^-?\d+$/.test(orderRaw)) {
    found.push(finding("Warning", "ORDER", ERROR_CODE.badFormat,
      `"${orderRaw}" does not parse as a whole number, so it becomes 0 `
      + "(SafeInt) and this item sorts to the front of its level.",
      "Use a whole number; the sheet's convention is gaps of ten."));
  } else if (orderRaw && Number(orderRaw) < 0) {
    found.push(finding("Warning", "ORDER", ERROR_CODE.badValue,
      "A negative order sorts ahead of everything and the add-in warns about "
      + "it (RibbonControlEntity.cs:512-516).",
      "Use zero or above."));
  }

  // ---- MENU_LAYOUT: names only, never numbers ------------------------------
  const layoutRaw = text(row, "MENU_LAYOUT");
  if (layoutRaw) {
    const layout = MENU_LAYOUTS.find(
      (l) => l.toLowerCase() === layoutRaw.toLowerCase());
    if (/^\d+$/.test(layoutRaw)) {
      found.push(finding("Warning", "MENU_LAYOUT", ERROR_CODE.badValue,
        `Numbers are REFUSED here even when they name a defined value — "2" `
        + "does not mean the third layout. The cell renders as Nested.",
        `Write the name: ${MENU_LAYOUTS.join(", ")}.`));
    } else if (!layout) {
      found.push(finding("Warning", "MENU_LAYOUT", ERROR_CODE.badValue,
        `"${layoutRaw}" is not a layout, so the menu renders as Nested and a `
        + "warning goes to the log nobody reads.",
        `The seven spellings are ${MENU_LAYOUTS.join(", ")}.`));
    } else if (known && !buildsAMenu(known)) {
      found.push(finding("Warning", "MENU_LAYOUT", CONSOLE_ONLY_CODE.notApplied,
        `A ${known} row is a click action, not a menu, so a layout on it has `
        + "no effect at all.",
        "Clear it, or move it to the Menu row above."));
    }
  }

  // ---- ICON: format traps only; there is no vocabulary --------------------
  const iconRaw = String(row?.ICON ?? "");
  if (iconRaw) {
    if (iconRaw !== iconRaw.trim()) {
      found.push(finding("Warning", "ICON", ERROR_CODE.badFormat,
        "Leading or trailing whitespace is kept and the lookup then misses.",
        "Trim it."));
    }
    if (iconRaw.length > 200) {
      found.push(finding("Error", "ICON", ERROR_CODE.tooLong,
        "Over 200 characters is refused outright.",
        "Use an imageMso id, or a file name like fuel.svg."));
    }
    if (iconRaw.includes("..")) {
      found.push(finding("Warning", "ICON", ERROR_CODE.badFormat,
        "\"..\" is a path traversal and the add-in warns about it.",
        "Use a plain file name."));
    }
    if (iconRaw.trim().endsWith(".")) {
      found.push(finding("Warning", "ICON", ERROR_CODE.badFormat,
        "A trailing dot with no extension is neither a file nor an Office id.",
        "Finish the extension, or drop the dot."));
    }
  }

  return found.sort((a, b) => RANK[b.severity] - RANK[a.severity]);
}

/** Walks up PARENT_KEY looking for `target`, naming the ring if it finds one. */
function walkToRoot(start, rows, target) {
  const path = [];
  let current = start;
  const seen = new Set();
  while (current) {
    const key = text(current, "ITEM_KEY");
    if (!key || seen.has(key.toLowerCase())) return null;
    seen.add(key.toLowerCase());
    path.push(key);
    const parentKey = text(current, "PARENT_KEY");
    if (!parentKey) return null;
    if (parentKey.toLowerCase() === String(target).toLowerCase()) {
      return [target, ...path.reverse()].join(" -> ");
    }
    current = (rows || []).find(
      (r) => text(r, "ITEM_KEY").toLowerCase() === parentKey.toLowerCase());
  }
  return null;
}

/** Does this row render anywhere at all? The question the sheet is worst at. */
export function rendersNowhere(found) {
  return found.some((f) => f.field === "CONTROL_KEY"
                        && f.code === CONSOLE_ONLY_CODE.silentDrop);
}

/** IS_ACTIVE, with the add-in's own default for a blank or unreadable cell. */
export function controlSwitchedOff(row) {
  return readBoolean(row?.IS_ACTIVE,
                     BOOLEAN_DEFAULTS["6.RibbonControls"].IS_ACTIVE) === false;
}
