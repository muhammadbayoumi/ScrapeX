// Transport to the local ScrapeX engine.
//
// Two routes to the SAME engine:
//   1. Native messaging  — Chrome starts the engine on demand; nothing to launch.
//   2. HTTP localhost    — the engine is already running via `scrapex ui`.
//
// Native is tried first and HTTP is the fallback, so a user who has not run the
// installer yet is never stranded.
//
// MV3 NOTE: the service worker may hibernate after ~30s, so no long-lived port is
// kept here. The side panel talks to the engine directly, one request at a time,
// and re-reads current state on reconnect — the engine owns the job, not us.

const HOST_NAME = "com.scrapex.engine";
export const PROTOCOL_VERSION = 1;

let nativeAvailable = null; // null = untested, true/false = known

function sendNative(message) {
  return new Promise((resolve, reject) => {
    let settled = false;
    const done = (fn, value) => { if (!settled) { settled = true; fn(value); } };
    try {
      chrome.runtime.sendNativeMessage(
        HOST_NAME,
        { ...message, protocol_version: PROTOCOL_VERSION },
        (response) => {
          if (chrome.runtime.lastError) {
            done(reject, new Error(chrome.runtime.lastError.message));
            return;
          }
          done(resolve, response);
        }
      );
    } catch (e) {
      done(reject, e);
    }
    // Chrome can leave the callback pending if the host dies on startup.
    setTimeout(() => done(reject, new Error("native host did not respond")), 5000);
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
  if (response && response.ok === false) throw new Error(response.detail || response.error);
  return response;
}

export async function sendCommand(message, httpFallback) {
  if (nativeAvailable !== false) {
    try {
      const response = unwrap(await sendNative(message));
      nativeAvailable = true;
      return response;
    } catch (e) {
      if (e instanceof VersionMismatchError) throw e;  // a real answer, not absence
      nativeAvailable = false;                          // not installed — fall back
    }
  }
  if (!httpFallback) throw new Error("the ScrapeX engine is not reachable");
  return httpFallback();
}

export function nativeStatus() {
  return nativeAvailable === null ? "unknown" : nativeAvailable ? "connected" : "unavailable";
}
