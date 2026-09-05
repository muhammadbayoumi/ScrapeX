// The button that proves the backup is sound must not fail on the backup it checks.
//
// "Fetch the latest backup" never restored anything — its own comment said so. It
// DOWNLOADED the archive and looked at `archive.size`, which on his 541,531,989-byte
// bundle asks a Chrome side panel to hold half a gigabyte. That is exactly what
// failed on the upload side on 2026-09-03, so the one control that can tell him his
// backup is sound would have failed on the backup it was checking.
//
// AND ASKING DRIVE IS THE STRONGER CHECK, not merely the cheaper one. A downloaded
// size catches a truncated DOWNLOAD. Drive's stored size catches a truncated UPLOAD
// — which is the failure that actually happened: a 0-byte archive reached Drive on
// 2026-08-30 with a pointer describing it as whole.

import {test} from "node:test";
import assert from "node:assert/strict";

import {verifyLatest, metadata, DriveError, LATEST, BUNDLE_FORMAT} from "../drive.js";

/** Drive, as far as these tests are concerned, plus a record of every URL asked. */
function drive({pointer, file}) {
  const asked = [];
  const fetchImpl = async (url) => {
    asked.push(String(url));
    const text = String(url);
    // The folder lookup and the pointer read, in the order drive.js makes them.
    if (text.includes("files?") && text.includes("mimeType")) {
      return json({files: [{id: "folder-1", name: "ScrapeX"}]});
    }
    if (text.includes("alt=media")) return json(pointer);
    if (text.includes(`files/${file.id}`)) return json(file);
    if (text.includes("files?")) {
      return json({files: [{id: "pointer-1", name: LATEST, size: "10"}]});
    }
    return json({files: []});
  };
  return {fetchImpl, asked};
}

function json(body) {
  return {
    ok: true, status: 200,
    headers: {get: () => null},
    json: async () => body,
    text: async () => JSON.stringify(body),
    blob: async () => new Blob([JSON.stringify(body)]),
  };
}

const POINTER = {
  file_id: "archive-1", bytes: 541531989, bundle_format: BUNDLE_FORMAT,
  created_at: "2026-09-03T13:15:01Z", engine_version: "0.4.7",
};

test("the check asks Drive and downloads nothing", async () => {
  const {fetchImpl, asked} = drive({
    pointer: POINTER,
    file: {id: "archive-1", name: "archive.zip", size: "541531989"},
  });

  const {held} = await verifyLatest("token", {fetchImpl});

  assert.equal(held.size, 541531989);
  const downloads = asked.filter(
    (url) => url.includes("alt=media") && url.includes("archive-1"));
  assert.deepEqual(downloads, [],
    `the check downloaded the archive: ${downloads.join(", ")}. The whole point is `
    + "that a half-gigabyte file can be verified without moving it.");
});

test("Drive's size is a STRING and comparing it raw would fail every healthy backup",
     async () => {
  // Drive returns `size` as a string. Compared with `!==` against the pointer's
  // number it is never equal, so a guard that skipped this would report every
  // sound backup as truncated — a check that fails on correct input is one people
  // learn to route around.
  const {fetchImpl} = drive({
    pointer: POINTER,
    file: {id: "archive-1", name: "archive.zip", size: "541531989"},
  });

  const held = await metadata("token", "archive-1", {fetchImpl});

  assert.equal(typeof held.size, "number");
  assert.equal(held.size, POINTER.bytes);
});

test("a truncated UPLOAD is caught, which downloading never could", async () => {
  // Drive holds less than the pointer promised: the upload stopped. The old check
  // downloaded whatever was there and compared it to the pointer, which catches a
  // truncated download — a different failure from the one that happened.
  const {fetchImpl} = drive({
    pointer: POINTER,
    file: {id: "archive-1", name: "archive.zip", size: "12345"},
  });

  await assert.rejects(
    () => verifyLatest("token", {fetchImpl}),
    (error) => error instanceof DriveError && error.kind === "truncated"
               && /12345/.test(error.message) && /541531989/.test(error.message));
});

test("an empty archive in Drive is refused and says what to do", async () => {
  const {fetchImpl} = drive({
    pointer: {...POINTER, bytes: 0},
    file: {id: "archive-1", name: "archive.zip", size: "0"},
  });

  await assert.rejects(
    () => verifyLatest("token", {fetchImpl}),
    (error) => error instanceof DriveError && error.kind === "empty"
               && /Take a new backup/.test(error.message));
});

test("a backup from a newer engine is still refused before anything else", async () => {
  const {fetchImpl} = drive({
    pointer: {...POINTER, bundle_format: BUNDLE_FORMAT + 1},
    file: {id: "archive-1", name: "archive.zip", size: "541531989"},
  });

  await assert.rejects(
    () => verifyLatest("token", {fetchImpl}),
    (error) => error instanceof DriveError && error.kind === "wrong-format");
});

test("no backup at all is a plain answer, not an error about a missing file", async () => {
  const fetchImpl = async (url) => (String(url).includes("mimeType")
    ? json({files: [{id: "folder-1", name: "ScrapeX"}]})
    : json({files: []}));

  await assert.rejects(
    () => verifyLatest("token", {fetchImpl}),
    (error) => error instanceof DriveError && error.kind === "no-backup");
});
