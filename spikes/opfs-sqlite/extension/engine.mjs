// Three OPFS-backed SQLite engines behind one interface, plus the OPFS
// primitives the experiments poke at directly:
//
//   wa-sqlite + OriginPrivateFileSystemVFS  — takes an existing file, slow
//   wa-sqlite + AccessHandlePoolVFS         — fast, cannot take a file
//   @sqlite.org/sqlite-wasm + OPFS SAH pool — fast, and has an import API
//
// The first is the one MASTER-PLAN.md names. The other two are here because a
// verdict drawn from one library's quirks would not be a verdict about OPFS.
//
// This module is imported by BOTH `worker.mjs` (a dedicated worker owned by an
// extension page) and `sw.js` (the MV3 service worker), because half of what
// the spike is trying to find out is whether those two contexts behave the
// same. Anything that differs between them has to differ here, in one place,
// or the comparison is not a comparison.

// STATIC imports, not `import()`. A module service worker may only use static
// imports — dynamic `import()` throws
// "import() is disallowed on ServiceWorkerGlobalScope by the HTML
// specification" (w3c/ServiceWorker#1356), measured on the first run of this
// spike. Since half the point is to compare the service worker with a
// dedicated worker, both engines have to be reachable the same way in both.
import waSqliteFactory from './vendor/wa-sqlite/dist/wa-sqlite-async.mjs';
import * as SQLite from './vendor/wa-sqlite/src/sqlite-api.js';
import { AccessHandlePoolVFS } from './vendor/wa-sqlite/src/examples/AccessHandlePoolVFS.js';
import { OriginPrivateFileSystemVFS } from './vendor/wa-sqlite/src/examples/OriginPrivateFileSystemVFS.js';
import sqlite3InitModule from './vendor/sqlite-wasm/index.mjs';

const VENDOR = new URL('./vendor/', import.meta.url);

// ---- OPFS primitives -------------------------------------------------------

export async function opfsRoot() {
  return navigator.storage.getDirectory();
}

/** Every file under OPFS, with its size. The ground truth for "did it fit?". */
export async function opfsTree(dir, prefix = '') {
  const out = [];
  for await (const [name, handle] of dir.entries()) {
    const path = `${prefix}/${name}`;
    if (handle.kind === 'file') {
      const file = await handle.getFile();
      out.push({ path, bytes: file.size });
    } else {
      out.push(...await opfsTree(handle, path));
    }
  }
  return out;
}

export async function estimate() {
  const e = await navigator.storage.estimate();
  return {
    quota: e.quota,
    usage: e.usage,
    // Chrome reports the per-bucket breakdown here; fileSystem is OPFS.
    usageDetails: e.usageDetails ? { ...e.usageDetails } : null,
    persisted: await navigator.storage.persisted?.().catch(() => null) ?? null,
  };
}

/**
 * Stream a URL straight into an OPFS file with a sync access handle.
 *
 * Deliberately chunked rather than `arrayBuffer()` then one write: the question
 * is whether a 75 MB warehouse can LAND in an extension, and a measurement that
 * needs 75 MB of heap to make the copy would be answering an easier question.
 */
export async function downloadToOpfs(url, path) {
  const root = await opfsRoot();
  const handle = await fileHandleAt(root, path, true);
  const t0 = performance.now();
  const response = await fetch(url);
  if (!response.ok) throw new Error(`${url} -> HTTP ${response.status}`);

  let access;
  let mode = 'sync-access-handle';
  try {
    access = await handle.createSyncAccessHandle();
  } catch (err) {
    // Reported, never silently swapped: which write path was available is
    // itself one of the findings.
    mode = `writable-stream (createSyncAccessHandle: ${err.name})`;
  }

  let written = 0;
  if (access) {
    access.truncate(0);
    const reader = response.body.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      written += access.write(value, { at: written });
    }
    access.flush();
    access.close();
  } else {
    const writable = await handle.createWritable();
    const reader = response.body.getReader();
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      await writable.write(value);
      written += value.byteLength;
    }
    await writable.close();
  }
  const ms = performance.now() - t0;
  return { path, bytes: written, ms: Math.round(ms), mode };
}

async function fileHandleAt(root, path, create) {
  const parts = path.split('/').filter(Boolean);
  const name = parts.pop();
  let dir = root;
  for (const part of parts) dir = await dir.getDirectoryHandle(part, { create });
  return dir.getFileHandle(name, { create });
}

export { fileHandleAt };

// ---- engine: wa-sqlite over OPFS ------------------------------------------

async function openWaSqlite(dbPath) {
  const module = await waSqliteFactory({
    locateFile: (file) => new URL(`wa-sqlite/dist/${file}`, VENDOR).href,
  });
  const sqlite3 = SQLite.Factory(module);
  sqlite3.vfs_register(new OriginPrivateFileSystemVFS(), true);
  const db = await sqlite3.open_v2(dbPath);

  return {
    engine: 'wa-sqlite',
    // No `version` field: `describe()` reads it out of the database with
    // `SELECT sqlite_version()`, which is the number that actually applies.
    async exec(sql, params = []) {
      const rows = [];
      for await (const stmt of sqlite3.statements(db, sql)) {
        if (params.length) sqlite3.bind_collection(stmt, params);
        while (await sqlite3.step(stmt) === SQLite.SQLITE_ROW) rows.push(sqlite3.row(stmt));
      }
      return rows;
    },
    async close() { await sqlite3.close(db); },
  };
}

// ---- engine: the SQLite project's own build, OPFS SAHPool VFS -------------

// One module instance and ONE pool per context, kept for the life of the
// worker. Not a tidiness measure: a second SQLite instance asking for the same
// SAH pool cannot acquire the pool files the first one holds, and fails with
// NoModificationAllowedError — the same exclusivity §3 measures, showing up
// between two copies of the library inside a single worker.
let sahPoolPromise = null;

async function openSahPool(dbPath, { importBytes = null, capacity = 12 } = {}) {
  const sqlite3 = await sqlite3InitModule();
  sahPoolPromise ??= sqlite3.installOpfsSAHPoolVfs({
    name: 'scrapex-spike',
    initialCapacity: capacity,
  });
  const pool = await sahPoolPromise;
  // "Results are undefined if the given db name refers to an opened db" — the
  // library's own warning. Re-importing over a file the pool already holds
  // throws NoModificationAllowedError, so an existing pool file is reused. The
  // list is reported either way: a phase that silently re-imported would be
  // timing a different database from the one it claims.
  const poolFiles = pool.getFileNames();
  let importState = 'not requested';
  if (importBytes) {
    if (poolFiles.includes(dbPath)) {
      importState = 'skipped: already in the pool';
    } else {
      try {
        await pool.importDb(dbPath, importBytes);
        importState = 'imported';
      } catch (err) {
        importState = `import refused (${err.name}); opening what the pool already has`;
      }
    }
  }
  const db = new pool.OpfsSAHPoolDb(dbPath);
  return {
    engine: 'sqlite-wasm-sahpool',
    version: sqlite3.version.libVersion,
    import_state: importState,
    pool_files_before: poolFiles,
    pool,
    async exec(sql, params = []) {
      return db.exec({
        sql,
        bind: params.length ? params : undefined,
        rowMode: 'array',
        returnValue: 'resultRows',
      });
    },
    async close() { db.close(); },
  };
}

// ---- engine: wa-sqlite's FAST OPFS VFS, and the migration it forces --------

/**
 * wa-sqlite's `AccessHandlePoolVFS` — sync access handles, no Asyncify, the
 * same design as the SQLite project's SAH pool and the reason to expect it to
 * be fast.
 *
 * It stores every database inside an opaque pool file whose first 4096 bytes
 * are a private header (path, flags, digest), so an existing 75 MB warehouse
 * CANNOT be handed to it as a file the way the plain OPFS VFS accepts one, and
 * wa-sqlite ships no import API. The only supported route is to let SQLite
 * build the database itself, which is what `copyFrom` does: attach the plain
 * OPFS copy and rebuild the warehouse table by table. How long that takes is
 * the migration cost Topology A would pay on every user's machine, so it is
 * measured rather than waved at.
 */
let ahpPoolPromise = null;

async function openAccessHandlePool(dbPath, { copyFrom = null, poolDir = 'ahp' } = {}) {
  const module = await waSqliteFactory({
    locateFile: (file) => new URL(`wa-sqlite/dist/${file}`, VENDOR).href,
  });
  const sqlite3 = SQLite.Factory(module);
  sqlite3.vfs_register(new OriginPrivateFileSystemVFS(), false);
  // Same reason as the SAH pool above: one pool per context, or the second
  // instance fights the first for the pool's own OPFS files.
  ahpPoolPromise ??= (async () => {
    const created = new AccessHandlePoolVFS(poolDir);
    await created.isReady;
    return created;
  })();
  const pool = await ahpPoolPromise;
  // The pool hands out one pre-opened OPFS file per SQLite file, and it starts
  // with six. A main database plus its rollback journal plus the attached
  // source plus temp files runs that close; the ceiling is raised here so a
  // capacity error cannot be mistaken for a storage limit.
  if (pool.getCapacity() < 16) await pool.addCapacity(16 - pool.getCapacity());
  sqlite3.vfs_register(pool, true);

  const FLAGS = SQLite.SQLITE_OPEN_CREATE | SQLite.SQLITE_OPEN_READWRITE | SQLite.SQLITE_OPEN_URI;
  const db = await sqlite3.open_v2(dbPath, FLAGS);

  const run = async (sql, params = []) => {
    const rows = [];
    for await (const stmt of sqlite3.statements(db, sql)) {
      if (params.length) sqlite3.bind_collection(stmt, params);
      while (await sqlite3.step(stmt) === SQLite.SQLITE_ROW) rows.push(sqlite3.row(stmt));
    }
    return rows;
  };

  let migration = null;
  if (copyFrom) {
    const already = (await run("SELECT count(*) FROM sqlite_master WHERE type='table'"))[0][0];
    if (already > 0) {
      migration = { skipped: 'pool already holds this database' };
    } else {
      migration = await rebuildInto(run, copyFrom);
    }
  }

  return {
    engine: 'wa-sqlite-accesshandlepool',
    migration,
    exec: run,
    async close() { await sqlite3.close(db); },
  };
}

/** Rebuild a warehouse from an attached source: DDL, then rows, then indexes. */
async function rebuildInto(run, sourcePath) {
  const t0 = performance.now();
  await run(`ATTACH DATABASE 'file:${sourcePath}?vfs=opfs' AS src`);
  const objects = await run(
    "SELECT type, name, sql FROM src.sqlite_master WHERE sql IS NOT NULL AND name NOT LIKE 'sqlite_%'");
  const tables = objects.filter((o) => o[0] === 'table');
  // Indexes, triggers and views go on AFTER the rows: building 59 indexes
  // incrementally across 197k inserts is the slow way round, and the triggers
  // are append-only guards that have nothing to say about a bulk load.
  const rest = objects.filter((o) => o[0] !== 'table');

  await run('PRAGMA foreign_keys = OFF');
  await run('BEGIN');
  for (const [, , sql] of tables) await run(sql);
  const ddl_ms = Math.round(performance.now() - t0);

  const t1 = performance.now();
  let rows = 0;
  for (const [, name] of tables) {
    await run(`INSERT INTO main."${name}" SELECT * FROM src."${name}"`);
    rows += (await run(`SELECT count(*) FROM main."${name}"`))[0][0];
  }
  const rows_ms = Math.round(performance.now() - t1);

  const t2 = performance.now();
  for (const [, , sql] of rest) await run(sql);
  await run('COMMIT');
  const index_ms = Math.round(performance.now() - t2);
  await run('DETACH DATABASE src');

  return {
    source: sourcePath,
    tables: tables.length,
    other_objects: rest.length,
    rows_copied: rows,
    ddl_ms,
    rows_ms,
    index_ms,
    total_ms: Math.round(performance.now() - t0),
  };
}

export async function openEngine(kind, dbPath, opts = {}) {
  if (kind === 'wa-sqlite') return openWaSqlite(dbPath, opts);
  if (kind === 'sahpool') return openSahPool(dbPath, opts);
  if (kind === 'ahp') return openAccessHandlePool(dbPath, opts);
  throw new Error(`unknown engine ${kind}`);
}

// ---- what every experiment wants to know about an opened database ---------

export async function describe(handle) {
  const one = async (sql) => (await handle.exec(sql))[0]?.[0];
  return {
    engine: handle.engine,
    sqlite: await one('SELECT sqlite_version()'),
    page_size: await one('PRAGMA page_size'),
    page_count: await one('PRAGMA page_count'),
    user_version: await one('PRAGMA user_version'),
    journal_mode: await one('PRAGMA journal_mode'),
    tables: await one("SELECT count(*) FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"),
    triggers: await one("SELECT count(*) FROM sqlite_master WHERE type='trigger'"),
    views: await one("SELECT count(*) FROM sqlite_master WHERE type='view'"),
    indexes: await one("SELECT count(*) FROM sqlite_master WHERE type='index'"),
    price_observation: await one('SELECT count(*) FROM price_observation'),
  };
}
