// The MV3 service worker: the context Topology A would actually run the engine
// in, and the one the plan never tested.
//
// What this file found, so the shape of it is not a surprise on the way down:
// a service worker can READ an OPFS SQLite database and cannot WRITE one.
// `createSyncAccessHandle()` is `[Exposed=DedicatedWorker]`, and a service
// worker cannot spawn a dedicated worker to borrow one. So there is no
// "half-written transaction survives a kill" test here — the transaction
// cannot start.
//
// A boot counter is kept in `chrome.storage.local` (`lives`) so that a worker
// which HAS been terminated says so the next time it is woken; without it, a
// death and a slow reply look the same from the driver.

import { describe, downloadToOpfs, estimate, openEngine, opfsRoot, opfsTree } from './engine.mjs';

const BOOT = Date.now();

// Which capabilities exist in THIS scope. Recorded at import time, because a
// service worker that dies loses the answer along with everything else.
const SCOPE = {
  scope: 'ServiceWorkerGlobalScope',
  // A dedicated worker is where OPFS sync access handles are meant to live.
  // If this is false, an MV3 engine cannot delegate its SQLite work.
  canSpawnWorker: typeof Worker !== 'undefined',
  hasOpfs: typeof navigator !== 'undefined' && !!navigator.storage?.getDirectory,
  hasWasm: typeof WebAssembly !== 'undefined',
  hasSharedArrayBuffer: typeof SharedArrayBuffer !== 'undefined',
};

let opened = null;

async function bumpLives() {
  const { lives = 0 } = await chrome.storage.local.get('lives');
  await chrome.storage.local.set({ lives: lives + 1, last_boot: BOOT });
  return lives + 1;
}
const livesPromise = bumpLives();

const COMMANDS = {
  async ping() {
    return { ...SCOPE, boot: BOOT, alive_ms: Date.now() - BOOT, lives: await livesPromise };
  },

  /**
   * Which OPFS write primitives exist in THIS scope.
   *
   * `FileSystemFileHandle.createSyncAccessHandle()` is `[Exposed=DedicatedWorker]`
   * in the File System Access spec. If it is missing here, and `Worker` is also
   * missing here, then the MV3 service worker cannot obtain one at all — not
   * directly, and not by delegating.
   */
  async opfsWriteCapabilities() {
    const root = await navigator.storage.getDirectory();
    const handle = await root.getFileHandle('capability-probe.bin', { create: true });
    const result = {
      createSyncAccessHandle: typeof handle.createSyncAccessHandle,
      createWritable: typeof handle.createWritable,
      canSpawnWorker: typeof Worker !== 'undefined',
    };
    try {
      const access = await handle.createSyncAccessHandle();
      access.close();
      result.sync_handle_acquired = true;
    } catch (err) {
      result.sync_handle_acquired = false;
      result.sync_handle_error = `${err.name}: ${String(err.message).slice(0, 160)}`;
    }
    await root.removeEntry('capability-probe.bin').catch(() => {});
    return result;
  },

  /** Can the service worker WRITE to the warehouse it just read? */
  async tryWrite() {
    if (!opened) throw new Error('open first');
    const key = `spike_sw_write_${BOOT}`;
    try {
      await opened.exec(
        'INSERT INTO scrapex_meta (key, value) VALUES (?, ?) '
        + 'ON CONFLICT(key) DO UPDATE SET value = excluded.value',
        [key, String(Date.now())]);
      const back = await opened.exec('SELECT value FROM scrapex_meta WHERE key = ?', [key]);
      return { wrote: true, read_back: back[0]?.[0] ?? null };
    } catch (err) {
      return { wrote: false, error_name: err.name, error: String(err.message).slice(0, 240) };
    }
  },

  async estimate() { return estimate(); },

  async tree() {
    const files = await opfsTree(await opfsRoot());
    return { total_files: files.length, total_bytes: files.reduce((n, f) => n + f.bytes, 0) };
  },

  async download({ url, path }) { return downloadToOpfs(url, path); },

  async open({ engine, dbPath, importUrl }) {
    let importBytes = null;
    if (importUrl) importBytes = new Uint8Array(await (await fetch(importUrl)).arrayBuffer());
    opened = await openEngine(engine, dbPath, { importBytes });
    return describe(opened);
  },

  async statement({ sql, params = [], repeats = 3 }) {
    if (!opened) throw new Error('open first');
    const ms = [];
    let rows = 0;
    for (let i = 0; i < repeats; i += 1) {
      const t0 = performance.now();
      rows = (await opened.exec(sql, params)).length;
      ms.push(Math.round((performance.now() - t0) * 10) / 10);
    }
    ms.sort((a, b) => a - b);
    return { rows, min_ms: ms[0], median_ms: ms[Math.floor(ms.length / 2)], max_ms: ms[ms.length - 1] };
  },

  /**
   * The hour-long-crawl question, in miniature.
   *
   * Ticks once a second doing ONLY OPFS work — no `chrome.*` call that would
   * reset the idle timer, because a crawl's inner loop is fetch + parse +
   * write, not extension API traffic. Each tick is flushed to storage so the
   * next life can read how far this one got. Returns only if it survives the
   * whole span; if the worker is killed the caller sees the connection drop,
   * which is the answer.
   */
  async heartbeat({ seconds = 60, path = 'heartbeat.log' }) {
    const root = await opfsRoot();
    const handle = await root.getFileHandle(path, { create: true });
    const started = Date.now();
    let tick = 0;
    for (;;) {
      const elapsed = Date.now() - started;
      if (elapsed >= seconds * 1000) break;
      // `createWritable`, not a sync access handle: the latter does not exist
      // in this scope (see `opfsWriteCapabilities`). And NO `chrome.*` call in
      // this loop — a crawl's inner loop is fetch, parse, write, and extension
      // API traffic is exactly what would reset the idle timer and answer an
      // easier question than the one being asked.
      const writable = await handle.createWritable({ keepExistingData: true });
      const line = new TextEncoder().encode(`${tick} ${elapsed} ${BOOT}\n`);
      await writable.write({ type: 'write', position: tick * 32, data: line });
      await writable.close();
      tick += 1;
      await new Promise((r) => setTimeout(r, 1000));
    }
    return { survived_seconds: Math.round((Date.now() - started) / 1000), ticks: tick, boot: BOOT };
  },

  /**
   * Is this the same life that ran the heartbeat?
   *
   * `this_boot === last_boot` and an unchanged `lives` mean the worker was
   * never terminated; a higher `lives` means it was, and the driver is talking
   * to its replacement.
   */
  async lastHeartbeat() {
    const local = await chrome.storage.local.get(['lives', 'last_boot']);
    return { ...local, this_boot: BOOT, alive_ms: Date.now() - BOOT };
  },
};

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  (async () => {
    try {
      const fn = COMMANDS[message.command];
      if (!fn) throw new Error(`unknown command ${message.command}`);
      sendResponse({ ok: true, result: await fn(message.args ?? {}) });
    } catch (err) {
      sendResponse({ ok: false, error: { name: err.name, message: String(err.message) } });
    }
  })();
  return true; // async response
});
