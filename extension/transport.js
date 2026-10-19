// Transport to the local ScrapeX engine — the CONTROL path.
//
// NOT two routes to the same engine. Two paths that carry different things and
// do not overlap:
//   CONTROL  native messaging, this file — start the engine, read and set
//            autostart, ping. Chrome starts the host on demand, and a host on
//            the machine is the only thing that can start a process for a page.
//   DATA     HTTP to 127.0.0.1, in engine.js and the panel — every source,
//            record, job and log the panel shows.
//
// This file used to export a sendCommand() that tried native first and fell
// back to HTTP for the SAME request. That only made sense while the host also
// answered data commands, and nothing in the extension ever called it. The
// host's data commands are gone (see scrapex/native.py) and so is it.
//
// MV3 NOTE: the service worker may hibernate after ~30s, so no long-lived port is
// kept here. The side panel talks to the engine directly, one request at a time,
// and re-reads current state on reconnect — the engine owns the job, not us.

import { STARTUP_DEADLINES } from "./startup.js";

const HOST_NAME = "com.scrapex.engine";
// The number the DATA path checks too: engine.js compares it against the one
// /api/health publishes. Its other half is PROTOCOL_VERSION in
// scrapex/native.py — the extension cannot import Python, so a Python test
// reads this line back and fails if the two ever diverge.
export const PROTOCOL_VERSION = 1;

// Every failure here used to arrive as one anonymous Error, and the panel had
// one branch for all of them: "the launcher is not installed". That sentence was
// printed on a machine where the launcher WAS installed, the host answered PING,
// and START_ENGINE replied ok — because a cold engine start takes longer than
// the five seconds this timeout allowed. Blaming a component that is working
// sends the owner to fix the wrong thing.
//
// So a rejection now SAYS WHICH FAILURE IT IS, on `kind`:
//   absent    Chrome could not find the host at all — the one case that is
//             genuinely "not installed"
//   forbidden the host exists and does not allow THIS extension id (a reload
//             from another folder gives the extension a new id)
//   crashed   the host started and died
//   timeout   nobody answered in the budget — usually still starting
const NATIVE_TIMEOUT_MS = 5000;
// THREE COMMANDS READ THE WHOLE WAREHOUSE, and a ping's five seconds is a lie
// about every one of them: the panel gave up, said what had happened, and the
// host went on to do it (#1706, #1094). Each is bounded by the work it does,
// and that work is O(FILE SIZE), so the numbers live with the other derived
// deadlines in `STARTUP_DEADLINES` rather than here.
//
// CHECK_STARTUP is a fresh process running `health(integrity=True)` on a file
// it has not opened -- the cold scan `integrityScan` is derived from. Measured
// 2026-10-17 through the host itself on a copy of his 2,232,049,664-byte
// warehouse: 26.9, 27.7 and 66.8 s cold.
const SCAN_TIMEOUT_MS = STARTUP_DEADLINES.integrityScan;
// START_ENGINE RUNS THAT SAME SCAN FIRST (`native.start_engine` calls
// `startup_check`), then spawns the engine and waits at most 3.5 s for its
// port. So it is the scan's budget, not a ping's and not its own: 66.8 s plus
// the 3.5 s was already past the 60 s it had.
const START_TIMEOUT_MS = SCAN_TIMEOUT_MS;
// UPGRADE_DATABASE copies the file, migrates it and scans it three times
// (`native.upgrade_database`): the warehouse-copy budget, derived at
// `warehouseCopy`, which the engine's own upgrade route has too.
const UPGRADE_TIMEOUT_MS = STARTUP_DEADLINES.warehouseCopy;

function nativeFailure(message) {
  const text = String(message || "");
  const error = new Error(text);
  if (/not found|no such native|Specified native messaging host not found/i.test(text)) {
    error.kind = "absent";
  } else if (/forbidden|not allowed|access to the specified native/i.test(text)) {
    error.kind = "forbidden";
  } else if (/exited|terminated|crashed|closed/i.test(text)) {
    error.kind = "crashed";
  } else {
    error.kind = "timeout";
  }
  return error;
}

function sendNative(message, timeoutMs = NATIVE_TIMEOUT_MS) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const done = (fn, value) => { if (!settled) { settled = true; fn(value); } };
    try {
      chrome.runtime.sendNativeMessage(
        HOST_NAME,
        { ...message, protocol_version: PROTOCOL_VERSION },
        (response) => {
          if (chrome.runtime.lastError) {
            done(reject, nativeFailure(chrome.runtime.lastError.message));
            return;
          }
          done(resolve, response);
        }
      );
    } catch (e) {
      done(reject, nativeFailure(e && e.message));
    }
    // Chrome can leave the callback pending if the host dies on startup.
    setTimeout(() => done(reject, nativeFailure("native host did not respond")),
               timeoutMs);
  });
}

// A version mismatch is surfaced as-is: the user is told which side is stale
// rather than being left with silently wrong behaviour.
export class VersionMismatchError extends Error {
  constructor(response) {
    super("The extension and the ScrapeX engine speak different protocol versions. " +
          "Update whichever is older.");
    this.hostVersion = response.host_protocol_version;
    this.clientVersion = response.client_protocol_version;
  }
}

function unwrap(response) {
  if (response && response.error === "version_mismatch") throw new VersionMismatchError(response);
  if (response && response.ok === false) {
    const error = new Error(response.detail || response.error);
    error.kind = response.error || "refused";
    error.action = response.action || "";
    error.databases = response.databases || null;
    throw error;
  }
  return response;
}

// The "start with Windows" launcher is a file on the machine; only the native
// host can read or write it. Native-only like startEngine — absence of the
// host throws, and the caller turns that into "run the one-time installer".
export function autostartStatus() {
  return sendNative({ command: "AUTOSTART_STATUS" }).then(unwrap);
}

export function setAutostart(enabled) {
  return sendNative({ command: "SET_AUTOSTART", enabled: !!enabled }).then(unwrap);
}

// Starting the engine is NATIVE-ONLY on purpose: the engine IS the data path,
// so when it is down there is nothing to fall back to. This either reaches the
// installed host or throws — and the caller turns that throw into "run the
// installer", which is the truthful next step.
export function startEngine() {
  // The long budget: this command waits for a real process to come up.
  return sendNative({ command: "START_ENGINE" }, START_TIMEOUT_MS).then((response) => {
    if (response && response.ok === false) {
      const refused = new Error(response.detail || response.error || "the host refused");
      refused.kind = response.error || "refused";
      refused.action = response.action || "";
      refused.databases = response.databases || null;
      // The host ANSWERED; it just could not start it.
      throw refused;
    }
    return response;
  });
}

// These two commands remain available when the HTTP engine is down. That is
// the important boundary: a failed startup must not hide the one action that
// can repair it behind the failed server.
export function checkStartup() {
  return sendNative({command: "CHECK_STARTUP"}, SCAN_TIMEOUT_MS).then(unwrap);
}

export function upgradeDatabase() {
  return sendNative({command: "UPGRADE_DATABASE"}, UPGRADE_TIMEOUT_MS).then(unwrap);
}
