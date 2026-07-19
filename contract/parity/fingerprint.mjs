// The JS engine's normalize/fingerprint — must match Python's frozen contract
// (contract/normalize-vectors.v1.json) byte-for-byte. This is the future TS
// browser engine's shared core, validated in CI against the frozen vectors.
import { createHash } from "node:crypto";

const DIGIT_MAP = {};
[..."٠١٢٣٤٥٦٧٨٩"].forEach((c, i) => (DIGIT_MAP[c] = String(i))); // Arabic-Indic
[..."۰۱۲۳۴۵۶۷۸۹"].forEach((c, i) => (DIGIT_MAP[c] = String(i))); // Eastern Arabic-Indic
DIGIT_MAP["٫"] = ".";
DIGIT_MAP["٬"] = ",";

export function foldDigits(text) {
  let out = "";
  for (const ch of text) out += DIGIT_MAP[ch] ?? ch;
  return out;
}

export function optionFingerprint(options) {
  return Object.keys(options)
    .sort()
    .map((k) => `${k.trim().toLowerCase()}=${foldDigits(String(options[k])).trim().toLowerCase()}`)
    .join("|");
}

// Canonical JSON == Python json.dumps(ensure_ascii=False, sort_keys=True, separators=(",",":")).
// Contract rule: record_hash receives CANONICAL STRINGS only (no language-native floats).
function canonical(v) {
  if (v === null) return "null";
  const t = typeof v;
  if (t === "string") return JSON.stringify(v);
  if (t === "boolean") return v ? "true" : "false";
  if (t === "number") return String(v);
  if (Array.isArray(v)) return "[" + v.map(canonical).join(",") + "]";
  if (t === "object") {
    return "{" + Object.keys(v).sort().map((k) => JSON.stringify(k) + ":" + canonical(v[k])).join(",") + "}";
  }
  throw new Error("unhandled type: " + t);
}

export function recordHash(payload) {
  return createHash("sha256").update(canonical(payload), "utf8").digest("hex");
}
