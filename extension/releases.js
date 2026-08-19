// What the newest ScrapeX-Engine is, read from where releases are actually cut.
//
// PLATFORM-PLAN Decision 4: releasing is manual, updating is not. A release is
// tagged; the tool reads it, says so, and installs it — the owner is never sent
// to a browser to fetch an installer.
//
// THE PUBLIC DELIVERY ENDPOINT, and it is deliberately not this code's own
// repository. ScrapeX's source goes private before the first release, and GitHub
// answers 404 on a private repository to anyone not signed in — which is every
// user. So releases go to `mbiX-hub`, which describes itself as the "public
// delivery endpoint" for the ecosystem and already carries a `ScrapeX/` folder
// beside `Xadd-in/`.
//
// A MANIFEST FILE, NOT THE RELEASES API, and this is the one thing copied
// wholesale from the Excel add-in's own release path. `api.github.com` allows
// SIXTY unauthenticated requests an hour PER IP ADDRESS. One owner never
// notices; an office, a VPN or a shared connection starts getting 403s that
// this code would report as a rate limit — correctly, and uselessly, because
// nothing the owner can do fixes it. `raw.githubusercontent.com` has no such
// limit, and the add-in has polled it across seventy-six releases.
//
// ITS OWN TIMEOUT, held separately from every other request the panel makes.
// mbiXaddin's UpdateService keeps a short check timeout apart from its client
// timeout for exactly this reason: a stalled fetch to a third party must never
// delay the thing the owner opened.

/** The public delivery endpoint. Named once; every URL below is built from it. */
export const PUBLIC_REPO = "muhammadbayoumi/mbiX-hub";

/** Where this product's own manifest lives, beside the add-in's. */
export const VERSION_MANIFEST =
  `https://raw.githubusercontent.com/${PUBLIC_REPO}/main/ScrapeX/json/version.json`;

/** Where a human goes: issues, releases, the install page. */
export const PUBLIC_HOME = `https://github.com/${PUBLIC_REPO}`;

export const CHECK_TIMEOUT_MS = 4000;

/** The product this manifest must be about. The hub serves several. */
export const PRODUCT = "scrapex-engine";

const VERSION = /^\d+\.\d+\.\d+$/;

/**
 * Turn the manifest into one of the states a reader can act on.
 *
 * Every branch is a DIFFERENT sentence, because "we don't know the latest
 * engine" has several causes and only one of them is anybody's fault:
 *
 *   ok            a published engine release, with its version
 *   none          nothing has been released for this product yet
 *   offline       the request never arrived
 *   unreadable    it answered with something this cannot use
 *
 * `status` and `body` are passed in rather than fetched, so the offline branch
 * can be tested honestly — a test that had to reach the network to prove what
 * happens when the network is unreachable would prove nothing.
 */
export function readVersionManifest(status, body) {
  if (status === 404) {
    // The file is not there. On this endpoint that means exactly one thing:
    // no engine release has been published yet. It is the true and complete
    // answer and must never be shown as an error.
    return { state: "none", detail: "No engine has been released yet." };
  }
  if (status !== 200) {
    return { state: "unreadable", detail: `The release manifest answered ${status}.` };
  }
  if (!body || typeof body !== "object") {
    return { state: "unreadable",
             detail: "The release manifest could not be read." };
  }

  // The hub serves the add-in's manifest from a sibling folder. Reading one as
  // the other would report a confident, wrong version — so the file must say
  // which product it is about, and this must agree.
  if (body.product !== PRODUCT) {
    return { state: "unreadable",
             detail: `That manifest is for ${body.product || "another product"}, ` +
                     `not the ScrapeX engine.` };
  }

  const version = typeof body.version === "string" ? body.version : "";
  if (!VERSION.test(version)) {
    return { state: "unreadable",
             detail: `The release manifest names no usable version (${version || "empty"}).` };
  }

  const installer = body.installer && typeof body.installer.url === "string"
    ? { name: body.installer.name || "scrapex-engine.exe",
        url: body.installer.url,
        bytes: Number(body.installer.bytes) || 0,
        sha256: typeof body.installer.sha256 === "string" ? body.installer.sha256 : "" }
    : null;

  return {
    state: "ok",
    version,
    tag: typeof body.tag === "string" ? body.tag : `engine-v${version}`,
    publishedAt: typeof body.published_at === "string" ? body.published_at : "",
    url: typeof body.release_url === "string" ? body.release_url : PUBLIC_HOME,
    // What this release will REFUSE to talk to, published beside it so the
    // panel can say "this needs a newer extension" BEFORE anything is
    // installed rather than after.
    minimumExtension: typeof body.minimum_extension_version === "string"
      ? body.minimum_extension_version : "",
    protocol: typeof body.protocol_version === "number" ? body.protocol_version : null,
    // Named even when absent: a release with no installer attached is a
    // release nobody can install, and that is worth seeing rather than
    // discovering at the moment of pressing Install.
    installer,
  };
}

/**
 * The URL actually fetched, carrying a cache key that changes once a minute.
 *
 * NOT AN OPTIMISATION AND NOT SUPERSTITION. raw.githubusercontent.com serves
 * this file through a CDN that caches it for about five minutes, and
 * `cache: "no-store"` does not reach that — it governs the BROWSER's cache
 * only. The manifest is rewritten in place on every release, so without this a
 * release can exist and be invisible for five minutes after it is published.
 *
 * The minute bucket rather than a unique timestamp is mbiXsite's own solution
 * to the same problem on the same endpoint, and its reasoning is worth keeping:
 * everyone loading within the same minute shares one cache entry, so the CDN
 * still absorbs almost every request. A per-request timestamp pushes every
 * caller through to origin, which measurably slowed the fetch and made the
 * timeout below far likelier to fire.
 */
export function manifestUrl(now = Date.now()) {
  return `${VERSION_MANIFEST}?t=${Math.floor(now / 60000)}`;
}

/** Ask the endpoint, and never let the asking delay anything. */
export async function latestEngineRelease(fetchImpl = fetch) {
  let response;
  try {
    response = await fetchImpl(manifestUrl(), {
      cache: "no-store",
      signal: AbortSignal.timeout(CHECK_TIMEOUT_MS),
    });
  } catch (_) {
    // A refusal, a DNS failure and the timeout above all land here, and from
    // the panel they are one fact: nobody answered.
    return { state: "offline",
             detail: "Could not reach the release endpoint. The engine you have " +
                     "keeps working." };
  }
  let body = null;
  try { body = await response.json(); } catch (_) { body = null; }
  return readVersionManifest(response.status, body);
}

/**
 * THE OTHER ENGINES. Candidates, not commitments — and not a register yet.
 *
 * docs/MASTER-PLAN.md §8.3 names seven backends and what each is for; this is
 * the six that are not ScrapeX itself, condensed to what the Engine page can
 * say without lying. There is no adapter descriptor to read (§8.4 is still a
 * design exercise) and nothing here is installable, so the page renders this
 * static table and keeps the note that says so.
 *
 * `licence` is the licence NOTE from §8.3, not a verdict: the plan's own column
 * heading is "licence note to verify per pinned release", and Firecrawl and
 * Heritrix both carry a caveat that a bare SPDX id would erase.
 *
 * When an engine register does exist, this table is what it replaces — one
 * export, one shape, six rows.
 */
export const ENGINE_CANDIDATES = [
  {
    id: "scrapy",
    name: "Scrapy",
    icon: "dns",
    role: "Structured spiders and large static crawls",
    shape: "Isolated Python worker",
    licence: "BSD-3-Clause",
  },
  {
    id: "crawlee",
    name: "Crawlee",
    icon: "account-tree",
    role: "Persistent queues, sessions and proxies",
    shape: "Python implementation first; a Node sidecar remains possible",
    licence: "Apache-2.0",
  },
  {
    id: "crawl4ai",
    name: "Crawl4AI",
    icon: "description",
    role: "Clean Markdown and document extraction",
    shape: "Isolated Python worker or local service",
    licence: "Apache-2.0 · attribution and dependencies still to review",
  },
  {
    id: "firecrawl",
    name: "Firecrawl",
    icon: "language",
    role: "Self-hosted or hosted scraping and crawling API",
    shape: "Separate HTTP provider, never copied into core",
    licence: "AGPL-3.0 · legal review before distribution",
  },
  {
    id: "katana",
    name: "Katana",
    icon: "search",
    role: "URL, route and endpoint discovery",
    shape: "Versioned Go binary or container adapter",
    licence: "MIT",
  },
  {
    id: "heritrix",
    name: "Heritrix",
    icon: "storage",
    role: "Web-scale archival crawling, WARC output",
    shape: "Separate Java or container archival pack",
    licence: "Apache-2.0 · some files under other licences",
  },
];
