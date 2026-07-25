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
// Starting an engine is not a ping: the host spawns it, waits for the port to
// answer, and only then replies. A cold interpreter opening two databases and
// running migrations is tens of seconds on a slow morning, so this command gets
// its own budget rather than being judged by a ping's.
const START_TIMEOUT_MS = 60000;

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

// The "start with Windows" launcher is a file on the machine; only the native
// host can read or write it. Native-only like startEngine — absence of the
// host throws, and the caller turns that into "run the one-time installer".
export function autostartStatus() {
  return sendNative({ command: "AUTOSTART_STATUS" }).then(unwrap);
}

export function setAutostart(enabled) {
  return sendNative({ command: "SET_AUTOSTART", enabled: !!enabled }).then(unwrap);
}

// Starting the engine is NATIVE-ONLY on purpose: the HTTP fallback IS the
// engine, so when it is down there is nothing to fall back to. This either
// reaches the installed host or throws — and the caller turns that throw into
// "run the installer", which is the truthful next step.
export function startEngine() {
  // The long budget: this command waits for a real process to come up.
  return sendNative({ command: "START_ENGINE" }, START_TIMEOUT_MS).then((response) => {
    if (response && response.ok === false) {
      const refused = new Error(response.detail || response.error || "the host refused");
      refused.kind = "refused";      // the host ANSWERED; it just could not start it
      throw refused;
    }
    nativeAvailable = true;
    return response;
  });
}
