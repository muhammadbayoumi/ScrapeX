// transport.js — just the extension-sync pair (CHECK_EXTENSION_SYNC,
// APPLY_EXTENSION_SYNC). The rest of this file's exports (autostart,
// startEngine, checkStartup, upgradeDatabase) are thin wrappers of the same
// shape and carry no test of their own; this covers the two added for the
// GitHub sync feature so the new native commands have a caller a grep finds
// and a test that would fail if the command name or the unwrap ever drifted.

import { test } from "node:test";
import assert from "node:assert/strict";

import { checkExtensionSync, applyExtensionSync } from "../transport.js";

function chromeHarness(respond) {
  return {
    runtime: {
      lastError: undefined,
      sendNativeMessage(_host, message, callback) {
        callback(respond(message));
      },
    },
  };
}

test("checkExtensionSync sends the command the native host actually answers", async () => {
  let sent = null;
  globalThis.chrome = chromeHarness((message) => {
    sent = message;
    return { ok: true, state: "up_to_date" };
  });

  const result = await checkExtensionSync();

  assert.equal(sent.command, "CHECK_EXTENSION_SYNC");
  assert.deepEqual(result, { ok: true, state: "up_to_date" });
});

test("applyExtensionSync sends the command the native host actually answers", async () => {
  let sent = null;
  globalThis.chrome = chromeHarness((message) => {
    sent = message;
    return { ok: true, state: "applied", head: "abc1234" };
  });

  const result = await applyExtensionSync();

  assert.equal(sent.command, "APPLY_EXTENSION_SYNC");
  assert.equal(result.head, "abc1234");
});

test("a refused sync surfaces the host's own reason, not a generic failure", async () => {
  globalThis.chrome = chromeHarness(() => (
    { ok: false, error: "merge_failed", detail: "fatal: something went wrong" }
  ));

  await assert.rejects(
    applyExtensionSync(),
    (error) => {
      assert.equal(error.message, "fatal: something went wrong");
      assert.equal(error.kind, "merge_failed");
      return true;
    },
  );
});
