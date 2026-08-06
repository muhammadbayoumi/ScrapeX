// What the newest ScrapeX-Engine is, read from where releases are actually cut.
//
// PLATFORM-PLAN Decision 4: releasing is manual, updating is not. A release is
// tagged on GitHub; the tool reads it, says so, and installs it — the owner is
// never sent to a browser to fetch an installer.
//
// THE EXTENSION ASKS, NOT THE ENGINE. The Engines page has to answer "what is
// available to install" on a machine with no engine on it at all, which is
// every machine for its first minute. An engine that fetched this could only
// ever answer once it was already there.
//
// ITS OWN TIMEOUT, held separately from every other request the panel makes.
// mbiXaddin's UpdateService keeps a short check timeout apart from its client
// timeout for exactly this reason: a stalled fetch to a third party must never
// be able to delay the thing the owner opened. Four seconds is longer than the
// API's normal answer by a wide margin and shorter than anyone waits for a
// panel to paint.

export const RELEASES_API =
  "https://api.github.com/repos/muhammadbayoumi/ScrapeX/releases/latest";

export const CHECK_TIMEOUT_MS = 4000;

// The tag a release carries. `engine-v0.4.0` is the engine's — PLATFORM-PLAN
// Decision 21 gives the two products separate tags, so a `scrapex-v…` tag on
// this feed is the EXTENSION's release and says nothing about the engine.
const ENGINE_TAG = /^engine-v(\d+\.\d+\.\d+)$/;

/**
 * Turn a GitHub response into one of the states a reader can act on.
 *
 * Every branch is a DIFFERENT sentence, because "we don't know the latest
 * engine" has four causes and only one of them is anybody's fault:
 *
 *   ok            a published engine release, with its version
 *   none          the feed answered, and nothing has been released yet
 *   rate-limited  GitHub is refusing to answer for a while
 *   offline       the request never arrived
 *   unreadable    it answered with something this cannot parse
 *
 * `status` and `body` are passed in rather than fetched so this is testable
 * without a network, which is the only way a test of the offline branch can be
 * honest.
 */
export function readLatestRelease(status, body, headers) {
  const remaining = headers && headers.get
    ? headers.get("x-ratelimit-remaining") : null;
  if (status === 403 && remaining === "0") {
    return { state: "rate-limited",
             detail: "GitHub is rate-limiting this network. It answers again " +
                     "within the hour; nothing is wrong with the engine." };
  }
  if (status === 404) {
    // A repository with no releases answers 404 on /releases/latest. That is
    // not an error and must never be shown as one: it is the true and complete
    // answer "nothing has been released yet".
    return { state: "none",
             detail: "No engine has been released yet." };
  }
  if (status !== 200) {
    return { state: "unreadable",
             detail: `GitHub answered ${status}.` };
  }

  const tag = body && typeof body.tag_name === "string" ? body.tag_name : "";
  const match = ENGINE_TAG.exec(tag);
  if (!match) {
    // A release exists and it is not an engine release — the extension's own
    // tag, or a hand-made one. Saying "unknown" here would be wrong twice: the
    // feed answered, and what it said was simply about something else.
    return { state: "none",
             detail: tag
               ? `The newest release is ${tag}, which is not an engine release.`
               : "No engine has been released yet." };
  }

  const asset = (body.assets || []).find(
    (a) => a && typeof a.name === "string" && a.name.endsWith(".exe"));
  return {
    state: "ok",
    version: match[1],
    tag,
    publishedAt: typeof body.published_at === "string" ? body.published_at : "",
    url: typeof body.html_url === "string" ? body.html_url : "",
    // Named even when absent: a release with no installer attached is a
    // release nobody can install, and that is worth seeing rather than
    // discovering at the moment of pressing Install.
    installer: asset ? { name: asset.name, url: asset.browser_download_url,
                         bytes: asset.size || 0 } : null,
  };
}

/** Ask GitHub, and never let the asking delay anything. */
export async function latestEngineRelease(fetchImpl = fetch) {
  let response;
  try {
    response = await fetchImpl(RELEASES_API, {
      headers: { "Accept": "application/vnd.github+json" },
      signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
    });
  } catch (_) {
    // A refusal, a DNS failure and the timeout above all land here, and from
    // the panel they are one fact: nobody answered.
    return { state: "offline",
             detail: "Could not reach GitHub. The engine you have keeps working." };
  }
  let body = null;
  try { body = await response.json(); } catch (_) { body = null; }
  return readLatestRelease(response.status, body, response.headers);
}
