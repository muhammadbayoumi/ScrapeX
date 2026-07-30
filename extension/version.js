// Which version this extension is, and whether it can work a given feature.
//
// The extension is the primary application, so this file answers the question
// FOR the panel and never on the engine's behalf: the ledger of what exists
// belongs to the engine and arrives over the wire (GET /api/version). What
// lives here is the extension's own version — read from the manifest Chrome
// loaded, which is the only number that describes what is actually running —
// and the compatibility rule, which has to be synchronous because it is checked
// at the moment a button is pressed.
//
// The rule exists twice, once in each language, and only one of them is Python
// (scrapex/version.py: capability_problem). Nothing but a shared vector file can
// notice when the two stop agreeing, so contracts/version-vectors.json pins
// both to the same sentences and extension/tests/version-compat.test.mjs fails
// this side of it. That is the same guardrail contract/parity/ puts under the
// normalize vectors, for the same reason.

// The manifest is the single place Chrome will tell you what it actually
// loaded. Reading it beats any constant here: a constant could say 0.2.0 in a
// folder Chrome loaded before the file changed, which is the precise lie this
// whole feature exists to make impossible.
export function installedVersion() {
  try {
    return (chrome.runtime.getManifest().version || "").trim();
  } catch (_) {
    // An older Chrome, or a page that is not an extension page. Unknown is said
    // as unknown; it is never guessed at, and never printed as a version.
    return "";
  }
}

export function parseVersion(value) {
  const parts = String(value || "").split(".");
  if (parts.length !== 3 || !parts.every((p) => /^\d+$/.test(p))) {
    throw new Error(
      `"${value}" is not a ScrapeX version: expected MAJOR.MINOR.PATCH, ` +
      `three integers separated by dots`);
  }
  return parts.map(Number);
}

// True when `left` is strictly behind `right`.
export function isOlder(left, right) {
  const a = parseVersion(left);
  const b = parseVersion(right);
  for (let i = 0; i < 3; i++) {
    if (a[i] !== b[i]) return a[i] < b[i];
  }
  return false;
}

// "" when this pair can work the capability, otherwise the refusal in words.
//
// `deployed` is what the ENGINE says it deploys, keyed by capability:
// `report.capabilities` reshaped, or null for an engine too old to publish any.
// Three refusals, three different remedies, and every one of them names BOTH
// versions — see the Python twin for why a bare number cannot be enough.
export function capabilityProblem(key, {extensionVersion, engineVersion, deployed,
                                        updateInstructions = ""} = {}) {
  const entry = deployed ? deployed[key] : null;
  const label = entry ? entry.summary : key;
  if (!deployed) {
    // Silence is not a mismatch — the same care engine.js takes with an absent
    // protocol_version. "Cannot say" and "does not have it" send the owner to
    // two different places, so they get two different sentences.
    return `«${label}» cannot be confirmed: the ScrapeX engine reports version ` +
      `${engineVersion} and is too old to say which features it deploys. ` +
      `This extension is ${extensionVersion}. Update the engine to ` +
      `${extensionVersion}.`;
  }
  if (!entry) {
    return `«${label}» is not deployed by this ScrapeX engine (${engineVersion}); ` +
      `this extension is ${extensionVersion}. Update the engine to ` +
      `${extensionVersion} or newer.`;
  }
  if (isOlder(extensionVersion, entry.since)) {
    return `«${label}» needs ScrapeX extension ${entry.since}; this extension ` +
      `is ${extensionVersion} and the engine is ${engineVersion}. ` +
      updateInstructions;
  }
  return "";
}

// The engine's capability list, in the shape capabilityProblem takes. Returns
// null for an engine that published no report at all, because null is what
// "this engine predates version reporting" has to stay distinguishable as.
export function deployedFrom(report) {
  if (!report || !Array.isArray(report.capabilities)) return null;
  const deployed = {};
  for (const capability of report.capabilities) {
    deployed[capability.key] = {since: capability.since, summary: capability.summary};
  }
  return deployed;
}
