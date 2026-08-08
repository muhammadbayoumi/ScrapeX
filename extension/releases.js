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

// THE PUBLIC HOME, and it is deliberately not this code's own repository.
//
// ScrapeX's source goes private before the first release. GitHub answers 404 on
// a private repository's releases endpoint to anyone not signed in — which is
// every user of this extension — and a 404 reads here as "nothing has been
// released yet". Every panel in the world would say the engine had never
// shipped, in a sentence that is honest about a fact that is wrong.
//
// So releases are published from the PUBLIC site, which is also where the
// install page, the privacy policy and the support page live. Named once here,
// so it cannot become three different answers.
export const PUBLIC_REPO = "muhammadbayoumi/mbiXsite";

// THE LIST, NOT `/releases/latest`, and this is the whole reason:
//
// That site carries SEVERAL products — ScrapeX and the Excel add-in, and more
// to come — so `/releases/latest` returns whatever was published last by
// ANYONE. Publish an add-in release after an engine release and the endpoint
// answers with the add-in; the tag would not match, and the panel would say
// "no engine has been released yet" with complete confidence and no truth in
// it at all.
//
// Listing and picking the newest engine tag is one extra field in the request
// and removes the failure entirely.
export const RELEASES_API =
  `https://api.github.com/repos/${PUBLIC_REPO}/releases?per_page=30`;

/** Where a human goes: issues, the install page, the policy. */
export const PUBLIC_HOME = `https://github.com/${PUBLIC_REPO}`;

export const CHECK_TIMEOUT_MS = 4000;

// The tag a release carries. `engine-v0.4.0` is the engine's — PLATFORM-PLAN
// Decision 21 gives the two products separate tags, so a `scrapex-v…` tag on
// this feed is the EXTENSION's release and says nothing about the engine.
// The tag an ENGINE release carries, and nothing else does. Decision 21 gives
// the extension its own `scrapex-v…` tag, and the other products on this site
// carry their own — so the tag is what says which product a release is for.
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
    // The LIST endpoint answers 200 with `[]` when a repository has no
    // releases, so a 404 here means the repository itself cannot be seen —
    // renamed, or private. Distinguishing it matters: "nothing released yet"
    // sends the owner to wait, and this sends him to look.
    return { state: "unreadable",
             detail: "The release feed could not be found. The repository was " +
                     "renamed, or is not public." };
  }
  if (status !== 200) {
    return { state: "unreadable",
             detail: `GitHub answered ${status}.` };
  }

  // A LIST, because this site publishes several products. GitHub returns it
  // newest first, so the first entry carrying an engine tag is the newest
  // engine release however many add-in releases were cut after it.
  const releases = Array.isArray(body) ? body : [];
  let release = null;
  let match = null;
  for (const candidate of releases) {
    if (!candidate || candidate.draft || candidate.prerelease) continue;
    const found = ENGINE_TAG.exec(
      typeof candidate.tag_name === "string" ? candidate.tag_name : "");
    if (found) { release = candidate; match = found; break; }
  }

  if (!release) {
    // The feed answered and had nothing for THIS product. Saying "unknown"
    // would be wrong twice: it answered, and what it said was about something
    // else.
    return { state: "none",
             detail: releases.length
               ? `Nothing on the release feed is an engine release yet — the ` +
                 `newest is ${releases[0].tag_name}, which is a different product.`
               : "No engine has been released yet." };
  }

  const asset = (release.assets || []).find(
    (a) => a && typeof a.name === "string" && a.name.endsWith(".exe"));
  return {
    state: "ok",
    version: match[1],
    tag: release.tag_name,
    publishedAt: typeof release.published_at === "string" ? release.published_at : "",
    url: typeof release.html_url === "string" ? release.html_url : "",
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
