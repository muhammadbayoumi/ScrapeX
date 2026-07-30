// The experiment runner. One dedicated worker, one command per message.
//
// A dedicated worker is where a real Topology A engine would have to do its
// SQLite work: `FileSystemSyncAccessHandle` is a worker-scope API, and an MV3
// service worker cannot spawn one of these (`Worker` is not defined there),
// which is itself measured in `sw.js`.

import {
  describe, downloadToOpfs, estimate, fileHandleAt, openEngine, opfsRoot, opfsTree,
} from './engine.mjs';

/** @type {{close():void}|null} */ let held = null;
/** @type {any} */ let opened = null;

// wa-sqlite's OPFS VFS reports the REAL reason a file would not open to
// `console.error` and then returns a bare SQLITE_CANTOPEN, so without this the
// only thing that reaches the driver is "unable to open database file".
const LOGS = [];
for (const level of ['error', 'warn']) {
  const original = console[level].bind(console);
  console[level] = (...args) => {
    LOGS.push(`${level}: ${args.map((a) => (a instanceof Error ? `${a.name}: ${a.message}` : String(a))).join(' ')}`);
    original(...args);
  };
}

const COMMANDS = {
  async ping() {
    return { scope: 'DedicatedWorker', canSpawnWorker: typeof Worker !== 'undefined' };
  },

  async logs() { return { logs: LOGS.slice(-30) }; },

  /** The same OPFS-write probe `sw.js` runs, for a side-by-side comparison. */
  async capabilities() {
    const root = await opfsRoot();
    const handle = await root.getFileHandle('capability-probe-worker.bin', { create: true });
    const out = {
      scope: 'DedicatedWorker',
      createSyncAccessHandle: typeof handle.createSyncAccessHandle,
      createWritable: typeof handle.createWritable,
      canSpawnWorker: typeof Worker !== 'undefined',
    };
    try {
      const access = await handle.createSyncAccessHandle();
      access.close();
      out.sync_handle_acquired = true;
    } catch (err) {
      out.sync_handle_acquired = false;
      out.sync_handle_error = `${err.name}: ${String(err.message).slice(0, 160)}`;
    }
    await root.removeEntry('capability-probe-worker.bin').catch(() => {});
    return out;
  },

  async estimate() {
    return estimate();
  },

  /**
   * Ask for the storage bucket to be exempt from eviction.
   *
   * Without this an origin's OPFS is "best-effort": Chrome may evict the whole
   * bucket under storage pressure, and for a price-HISTORY warehouse that is
   * the difference between a cache and a record. Asked for explicitly so the
   * answer is measured rather than assumed from the `unlimitedStorage`
   * permission being present.
   */
  async persist() {
    // `StorageManager.persist()` is exposed to Window only — in a worker the
    // method is simply absent, so an engine running where OPFS actually lives
    // cannot ask for its own storage to be protected. Reported, not thrown.
    if (typeof navigator.storage.persist !== 'function') {
      return {
        available_in_worker: false,
        note: 'navigator.storage.persist is not a function in a DedicatedWorker',
        persisted: await navigator.storage.persisted(),
      };
    }
    const before = await navigator.storage.persisted();
    const granted = await navigator.storage.persist();
    return {
      available_in_worker: true,
      persisted_before: before,
      persist_granted: granted,
      persisted_after: await navigator.storage.persisted(),
    };
  },

  async tree({ list = 12 } = {}) {
    const files = await opfsTree(await opfsRoot());
    // Grouped, not listed: after the journal experiment this is 3,584 entries,
    // and 3,570 near-identical filenames in the committed evidence would bury
    // the four that matter.
    const groups = {};
    for (const f of files) {
      const top = f.path.split('/')[1];
      groups[top] ??= { files: 0, bytes: 0 };
      groups[top].files += 1;
      groups[top].bytes += f.bytes;
    }
    return {
      total_files: files.length,
      total_bytes: files.reduce((n, f) => n + f.bytes, 0),
      by_top_level: groups,
      largest: [...files].sort((a, b) => b.bytes - a.bytes).slice(0, list),
    };
  },

  async download({ url, path }) {
    return downloadToOpfs(url, path);
  },

  async open({ engine, dbPath, importUrl, copyFrom = null }) {
    let importBytes = null;
    let fetch_ms = 0;
    if (importUrl) {
      const t0 = performance.now();
      importBytes = new Uint8Array(await (await fetch(importUrl)).arrayBuffer());
      fetch_ms = Math.round(performance.now() - t0);
    }
    const t1 = performance.now();
    opened = await openEngine(engine, dbPath, { importBytes, copyFrom });
    const open_ms = Math.round(performance.now() - t1);
    const t2 = performance.now();
    const shape = await describe(opened);
    return {
      ...shape,
      fetch_ms,
      open_ms,
      describe_ms: Math.round(performance.now() - t2),
      // Engine-specific provenance: which file was actually opened, and what it
      // cost to get it there. Without these a timing could belong to a database
      // other than the one the phase names.
      import_state: opened.import_state ?? null,
      pool_files_before: opened.pool_files_before ?? null,
      migration: opened.migration ?? null,
    };
  },

  async close() {
    if (opened) await opened.close();
    opened = null;
    return { closed: true };
  },

  /**
   * Replay a captured Python statement trace and time it.
   *
   * `transaction: true` reproduces `ingest_payloads`, which runs the whole
   * batch inside one transaction; replaying 18k statements in autocommit would
   * be measuring 18k fsyncs against Python's one, which is not the same job.
   */
  async trace({ statements, repeats = 1, transaction = false, collect = false }) {
    if (!opened) throw new Error('open the database first');
    const runs = [];
    for (let i = 0; i < repeats; i += 1) {
      const per = [];
      const t0 = performance.now();
      if (transaction) await opened.exec('BEGIN');
      let rows = 0;
      for (const stmt of statements) {
        const s0 = performance.now();
        const out = await opened.exec(stmt.sql, stmt.params ?? []);
        per.push(Math.round((performance.now() - s0) * 100) / 100);
        rows += out.length;
      }
      if (transaction) await opened.exec('COMMIT');
      runs.push({
        total_ms: Math.round((performance.now() - t0) * 10) / 10,
        rows_returned: rows,
        per_statement_ms: collect ? per : undefined,
      });
    }
    return { runs, statements: statements.length };
  },

  /** One statement, timed on its own, the way baseline.py times its two. */
  async statement({ sql, params = [], repeats = 5 }) {
    if (!opened) throw new Error('open the database first');
    const ms = [];
    let rows = 0;
    for (let i = 0; i < repeats; i += 1) {
      const t0 = performance.now();
      rows = (await opened.exec(sql, params)).length;
      ms.push(Math.round((performance.now() - t0) * 10) / 10);
    }
    ms.sort((a, b) => a - b);
    return {
      rows,
      repeats,
      min_ms: ms[0],
      median_ms: ms[Math.floor(ms.length / 2)],
      max_ms: ms[ms.length - 1],
    };
  },

  /** Take an exclusive sync access handle and KEEP it, for the lane test. */
  async hold({ path }) {
    const root = await opfsRoot();
    const handle = await fileHandleAt(root, path, true);
    held = await handle.createSyncAccessHandle();
    return { path, size: held.getSize() };
  },

  async release() {
    if (held) held.close();
    held = null;
    return { released: true };
  },

  /** Try to take a SECOND handle on a file this or another context holds. */
  async contend({ path }) {
    const root = await opfsRoot();
    const handle = await fileHandleAt(root, path, true);
    const t0 = performance.now();
    try {
      const second = await handle.createSyncAccessHandle();
      second.close();
      return { acquired: true, ms: Math.round(performance.now() - t0) };
    } catch (err) {
      return {
        acquired: false,
        error_name: err.name,
        error_message: String(err.message).slice(0, 200),
        ms: Math.round(performance.now() - t0),
      };
    }
  },

  /**
   * The resume journal, as OPFS files: one JSON payload per fetched page,
   * exactly the shape `scrapex/localinbox.py` writes to disk today.
   */
  async journal({ pages, bytesPerPage, dir = 'job-journal/ELBUROJ' }) {
    const root = await opfsRoot();
    let target = root;
    for (const part of dir.split('/').filter(Boolean)) {
      target = await target.getDirectoryHandle(part, { create: true });
    }
    // Sized to `bytesPerPage` exactly, by measuring the envelope and padding to
    // fit — the default is the real journal's mean page (930,534 bytes over 871
    // pages), and a payload 15% under that would quietly understate the cost.
    const envelope = JSON.stringify({ payload_version: 6, filler: '' }).length;
    const body = new TextEncoder().encode(JSON.stringify({
      payload_version: 6,
      filler: 'x'.repeat(Math.max(0, bytesPerPage - envelope)),
    }));
    const t0 = performance.now();
    for (let i = 0; i < pages; i += 1) {
      const fh = await target.getFileHandle(`t-${String(i).padStart(20, '0')}__page.json`, { create: true });
      const access = await fh.createSyncAccessHandle();
      access.truncate(0);
      access.write(body, { at: 0 });
      access.flush();
      access.close();
    }
    const write_ms = Math.round(performance.now() - t0);

    // Resume reads the skip set by SCANNING FILENAMES (localinbox.list_tokens).
    const t1 = performance.now();
    let counted = 0;
    for await (const _name of target.keys()) counted += 1;
    return {
      pages, bytes_per_page: body.byteLength, write_ms,
      write_ms_per_page: Math.round((write_ms / pages) * 100) / 100,
      list_ms: Math.round(performance.now() - t1), listed: counted,
    };
  },

  /** How much will OPFS actually take? Write until it refuses. */
  async quotaProbe({ chunkMiB = 64, maxMiB = 8192, path = 'quota-probe.bin' }) {
    const root = await opfsRoot();
    const handle = await fileHandleAt(root, path, true);
    const access = await handle.createSyncAccessHandle();
    access.truncate(0);
    // `x << 20` is a 32-bit signed op in JS: 6144 << 20 wraps to -2147483648
    // and the loop below never runs. Multiplication, not shifting, for
    // anything that can exceed 2 GiB.
    const MIB = 1024 * 1024;
    const chunk = new Uint8Array(chunkMiB * MIB);
    const ceiling = maxMiB * MIB;
    let written = 0;
    let stopped = `reached the ${maxMiB} MiB ceiling this probe set`;
    const t0 = performance.now();
    try {
      while (written < ceiling) {
        access.write(chunk, { at: written });
        written += chunk.byteLength;
      }
      access.flush();
    } catch (err) {
      stopped = `${err.name}: ${String(err.message).slice(0, 160)}`;
    }
    const ms = Math.round(performance.now() - t0);
    access.close();
    const after = await estimate();
    await (await opfsRoot()).removeEntry(path).catch(() => {});
    return {
      written_bytes: written,
      written_mib: Math.floor(written / MIB),
      stopped,
      ms,
      estimate_after: after,
    };
  },

  async wipe() {
    const root = await opfsRoot();
    const removed = [];
    for await (const [name] of root.entries()) {
      await root.removeEntry(name, { recursive: true }).catch((e) => removed.push(`${name}: ${e.name}`));
      removed.push(name);
    }
    return { removed };
  },
};

self.onmessage = async (event) => {
  const { id, command, args } = event.data;
  try {
    const fn = COMMANDS[command];
    if (!fn) throw new Error(`unknown command ${command}`);
    self.postMessage({ id, ok: true, result: await fn(args ?? {}) });
  } catch (err) {
    self.postMessage({
      id,
      ok: false,
      error: {
        name: err.name,
        message: String(err.message),
        stack: String(err.stack).slice(0, 900),
        logs: LOGS.slice(-10),
      },
    });
  }
};
