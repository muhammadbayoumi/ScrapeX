// CI PARITY GATE: the JS engine must reproduce the FROZEN contract vectors
// byte-for-byte. Run: node contract/parity/parity.test.mjs  (exit 1 on any diff).
import { readFileSync } from "node:fs";
import { foldDigits, optionFingerprint, recordHash } from "./fingerprint.mjs";

const V = JSON.parse(readFileSync(new URL("../normalize-vectors.v1.json", import.meta.url), "utf8"));
let fail = 0;
const groups = {};
function check(group, name, got, exp) {
  groups[group] ??= { pass: 0, fail: 0 };
  if (got === exp) groups[group].pass++;
  else { groups[group].fail++; fail++; console.log(`  FAIL [${group}] ${name}\n     py: ${exp}\n     js: ${got}`); }
}

for (const c of V.fold) check("foldDigits", JSON.stringify(c.in), foldDigits(c.in), c.out);
for (const c of V.fingerprint) check("optionFingerprint", JSON.stringify(c.in), optionFingerprint(c.in), c.out);
for (const c of V.record_hash) check("recordHash", JSON.stringify(c.in), recordHash(c.in), c.out);

console.log(`\n=== contract parity (JS vs frozen v${V.contract_version}) ===`);
for (const [g, r] of Object.entries(groups)) console.log(`  ${r.fail ? "FAIL" : "PASS"}  ${g}: ${r.pass}/${r.pass + r.fail}`);
process.exit(fail ? 1 : 0);
