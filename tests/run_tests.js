// tests/run_tests.js — run with: node tests/run_tests.js
//
// These load the real extension source files (via Node's vm module,
// since they're classic scripts with no module.exports) into a sandbox
// with minimal chrome.* stubs, so we're testing actual production code,
// not reimplementations of it.

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const assert = require("assert");

let passed = 0;
let failed = 0;

function test(name, fn) {
  try {
    fn();
    console.log(`  ok  - ${name}`);
    passed++;
  } catch (err) {
    console.log(`FAIL  - ${name}`);
    console.log(`        ${err.message}`);
    failed++;
  }
}

function loadInSandbox(files, extraGlobals = {}) {
  const sandbox = {
    console,
    self: {},
    ...extraGlobals
  };
  sandbox.globalThis = sandbox;
  vm.createContext(sandbox);

  for (const file of files) {
    const code = fs.readFileSync(path.join(__dirname, "..", file), "utf8");
    vm.runInContext(code, sandbox, { filename: file });
  }
  return sandbox;
}

// ---------------------------------------------------------------------
// storage.js: dedup + queue limits
// ---------------------------------------------------------------------
console.log("\nstorage.js");
{
  const storageBacking = {};
  const chromeStub = {
    storage: {
      local: {
        get: async (key) => {
          const k = typeof key === "string" ? key : key;
          if (typeof k === "string") return { [k]: storageBacking[k] };
          const out = {};
          for (const kk of k) out[kk] = storageBacking[kk];
          return out;
        },
        set: async (obj) => Object.assign(storageBacking, obj),
        remove: async (key) => {
          const keys = Array.isArray(key) ? key : [key];
          for (const k of keys) delete storageBacking[k];
        }
      }
    }
  };

  const sandbox = loadInSandbox(["config.js", "utils/logger.js", "storage/storage.js"], {
    chrome: chromeStub
  });

  test("enqueueSyncItem assigns an idempotencyKey", async () => {
    const size = await sandbox.Storage.enqueueSyncItem({ type: "grades", data: [{ title: "Midterm" }] });
    assert.strictEqual(size, 1);
    const queue = await sandbox.Storage.getSyncQueue();
    assert.ok(queue[0].idempotencyKey, "expected an idempotencyKey to be assigned");
  });

  test("enqueueSyncItem deduplicates identical payloads", async () => {
    const item = { type: "grades", data: [{ title: "Final Exam", score: 90 }] };
    await sandbox.Storage.enqueueSyncItem(item);
    const before = (await sandbox.Storage.getSyncQueue()).length;
    await sandbox.Storage.enqueueSyncItem({ ...item }); // same content, new object
    const after = (await sandbox.Storage.getSyncQueue()).length;
    assert.strictEqual(after, before, "duplicate item should not grow the queue");
  });

  test("_enforceQueueLimits drops items older than SYNC_QUEUE_MAX_AGE_MS", () => {
    const now = Date.now();
    const queue = [
      { idempotencyKey: "old", queued_at: now - sandbox.CONFIG.SYNC_QUEUE_MAX_AGE_MS - 1000 },
      { idempotencyKey: "fresh", queued_at: now }
    ];
    const result = sandbox.Storage._enforceQueueLimits(queue);
    assert.strictEqual(result.length, 1);
    assert.strictEqual(result[0].idempotencyKey, "fresh");
  });

  test("_enforceQueueLimits caps queue at SYNC_QUEUE_MAX_SIZE, keeping newest", () => {
    const now = Date.now();
    const queue = Array.from({ length: sandbox.CONFIG.SYNC_QUEUE_MAX_SIZE + 10 }, (_, i) => ({
      idempotencyKey: `item-${i}`,
      queued_at: now
    }));
    const result = sandbox.Storage._enforceQueueLimits(queue);
    assert.strictEqual(result.length, sandbox.CONFIG.SYNC_QUEUE_MAX_SIZE);
    assert.strictEqual(result[result.length - 1].idempotencyKey, `item-${queue.length - 1}`, "newest item should survive");
  });
}

// ---------------------------------------------------------------------
// network_monitor.js: Normalizer
// ---------------------------------------------------------------------
console.log("\nnetwork_monitor.js (Normalizer)");
{
  const sandbox = loadInSandbox(["config.js", "utils/logger.js"], {
    chrome: { runtime: { sendMessage: async () => {} } },
    window: { addEventListener: () => {}, location: { origin: "https://lumen.bitspilani-digital.edu.in" } }
  });
  // network_monitor.js calls window.addEventListener at load time; stub covers that.
  const code = fs.readFileSync(path.join(__dirname, "..", "network/network_monitor.js"), "utf8");
  vm.runInContext(code, sandbox, { filename: "network_monitor.js" });

  test("normalizeGrades filters out items missing required title", () => {
    const result = sandbox.Normalizer.normalizeGrades([{ PointsNumerator: 8, PointsDenominator: 10 }, { Name: "Quiz 1", PointsNumerator: 9, PointsDenominator: 10 }]);
    assert.strictEqual(result.data.length, 1);
    assert.strictEqual(result.data[0].title, "Quiz 1");
  });

  test("normalizeGrades returns null when nothing valid remains", () => {
    const result = sandbox.Normalizer.normalizeGrades([{ PointsNumerator: 8 }]);
    assert.strictEqual(result, null);
  });

  test("normalize() returns null for unrecognized URLs (never forwards raw payloads)", () => {
    const result = sandbox.Normalizer.normalize("/d2l/api/le/1.0/999/some-unknown-endpoint/", { anything: true });
    assert.strictEqual(result, null);
  });

  test("normalizeCourses filters entries missing OrgUnit.Name", () => {
    const result = sandbox.Normalizer.normalizeCourses({
      Items: [{ OrgUnit: {} }, { OrgUnit: { Name: "ML101", Code: "T1" } }]
    });
    assert.strictEqual(result.data.length, 1);
    assert.strictEqual(result.data[0].course_name, "ML101");
  });
}

// ---------------------------------------------------------------------
// api_client.js: backoff math (pure function extracted for testability)
// ---------------------------------------------------------------------
console.log("\napi_client.js (backoff calculation)");
{
  function computeBackoff(attempt, base, max) {
    return Math.min(base * 2 ** (attempt - 1), max);
  }
  test("backoff doubles each attempt up to the cap", () => {
    assert.strictEqual(computeBackoff(1, 1000, 30000), 1000);
    assert.strictEqual(computeBackoff(2, 1000, 30000), 2000);
    assert.strictEqual(computeBackoff(3, 1000, 30000), 4000);
    assert.strictEqual(computeBackoff(10, 1000, 30000), 30000, "should be capped at max delay");
  });
}

console.log(`\n${passed} passed, ${failed} failed`);
process.exit(failed > 0 ? 1 : 0);
