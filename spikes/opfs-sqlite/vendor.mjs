// Copy the two WASM SQLite builds out of node_modules and into the extension.
//
// An unpacked MV3 extension can only load modules from inside its own
// directory, so `extension/vendor/` is a staging area, not a checked-in copy —
// `.gitignore` keeps it out of the repo and `npm run vendor` refills it.
import { cp, mkdir, rm, stat } from 'node:fs/promises';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const OUT = join(HERE, 'extension', 'vendor');

const COPIES = [
  // wa-sqlite: the build MASTER-PLAN names. `src/` is needed as well as
  // `dist/`, because the OPFS VFSes ship as example source, not as bundles.
  ['node_modules/wa-sqlite/dist', 'wa-sqlite/dist'],
  ['node_modules/wa-sqlite/src', 'wa-sqlite/src'],
  // The SQLite project's own WASM build, carried as a second opinion so the
  // verdict is about OPFS and MV3 rather than about one library's quirks.
  ['node_modules/@sqlite.org/sqlite-wasm/dist', 'sqlite-wasm'],
];

await rm(OUT, { recursive: true, force: true });
await mkdir(OUT, { recursive: true });
for (const [from, to] of COPIES) {
  const src = join(HERE, from);
  await stat(src); // fail loudly if `npm install` has not run
  await cp(src, join(OUT, to), { recursive: true });
  console.log(`vendored ${from} -> extension/vendor/${to}`);
}
