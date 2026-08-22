/**
 * stack/seed.js — owner C. SRS §4 (Data Model), Risk R10, Risk R11.
 *
 * Run with:  mongosh "mongodb://localhost:27017/?directConnection=true" stack/seed.js
 * or:        bash stack/seed.sh
 *
 * Creates the four collections with the types their access patterns force, the four
 * indexes, and both Atlas Search indexes — then BLOCKS until the search indexes report
 * status READY and queryable true.
 *
 * That blocking poll is the whole point of this file. A $vectorSearch against a
 * non-queryable index returns EMPTY RESULTS, NOT AN ERROR (R10). It looks exactly like
 * a broken detector and sends the team debugging the wrong layer for half an hour.
 *
 * Idempotent: safe to re-run. Pass --eval 'DROP_DECISIONS=true' to re-drop `decisions`.
 * Note that dropping `decisions` fires an `invalidate` on the console's change stream —
 * services/inspect/stream.py handles that with the resumeAfter -> startAfter transition
 * (R11). Without it the console dies permanently on the first re-seed.
 */

/* eslint-disable no-undef */
const DB = "airlock";
const INDEX_READY_TIMEOUT_MS = 300000; // 5 min — index builds are async
const POLL_INTERVAL_MS = 2000;

const log = (m) => print(`[seed] ${m}`);
const ok = (m) => print(`[seed] ✓ ${m}`);
const warn = (m) => print(`[seed] ! ${m}`);

db = db.getSiblingDB(DB);

// ---------------------------------------------------------------------------
// 0. Optional targeted drops
// ---------------------------------------------------------------------------
const dropDecisions = typeof DROP_DECISIONS !== "undefined" && DROP_DECISIONS === true;
const dropAll = typeof DROP_ALL !== "undefined" && DROP_ALL === true;

if (dropAll) {
  warn("DROP_ALL set — dropping every airlock collection");
  ["policy_corpus", "decisions", "inspect_metrics", "benign_eval"].forEach((c) => {
    db.getCollection(c).drop();
  });
} else if (dropDecisions) {
  warn("DROP_DECISIONS set — dropping `decisions` (console will see an invalidate)");
  db.decisions.drop();
}

const existing = db.getCollectionNames();
const has = (n) => existing.indexOf(n) !== -1;

// ---------------------------------------------------------------------------
// 1. Collections — the three-way split by access pattern (SRS §4)
//
//    Time-series collections support NEITHER change streams NOR Search/Vector Search
//    NOR CSFLE. No single collection can be searchable, watchable and time-series.
//    Hence the split. This is a design decision, not an accident — do not "simplify" it.
// ---------------------------------------------------------------------------

// policy_corpus — regular. Needs $search + $vectorSearch. Impossible on time-series.
if (!has("policy_corpus")) {
  db.createCollection("policy_corpus");
  ok("created policy_corpus (regular)");
} else ok("policy_corpus exists");

// decisions — regular. Needs CHANGE STREAMS for the live console. Impossible on time-series.
if (!has("decisions")) {
  db.createCollection("decisions");
  ok("created decisions (regular — change streams)");
} else ok("decisions exists");

// benign_eval — regular, and deliberately SEPARATE from decisions: the 1000-doc harness
// burst would roll the single-node oplog and kill the console's resume token (R11).
if (!has("benign_eval")) {
  db.createCollection("benign_eval");
  ok("created benign_eval (regular — isolated from the console's oplog)");
} else ok("benign_eval exists");

// inspect_metrics — TIME-SERIES. Append-only telemetry: columnar buckets,
// $setWindowFields, and TTL expiry for free.
if (!has("inspect_metrics")) {
  db.createCollection("inspect_metrics", {
    timeseries: { timeField: "ts", metaField: "meta", granularity: "seconds" },
    expireAfterSeconds: 86400,
  });
  ok("created inspect_metrics (time-series, 24h TTL)");
} else ok("inspect_metrics exists");

// ---------------------------------------------------------------------------
// 2. Regular indexes
// ---------------------------------------------------------------------------
db.decisions.createIndex({ payload_sha256: 1 }, { name: "cache_key" }); // instant-block cache, ~1 ms
db.decisions.createIndex({ ts: -1 }, { name: "console_backfill" });
db.benign_eval.createIndex({ verdict: 1 }, { name: "verdict" });
db.policy_corpus.createIndex({ kind: 1, class: 1 }, { name: "kind_class" });
ok("regular indexes created");

// ---------------------------------------------------------------------------
// 3. Atlas Search indexes
//
//    Declare ALL FOUR filter paths NOW. Adding one later is an index rebuild you will
//    not have time for after 16:00.
//    cosine, because bge-small is trained for it and MongoDB does not normalise for you.
// ---------------------------------------------------------------------------
const searchIndexes = db.policy_corpus.getSearchIndexes().map((i) => i.name);

if (searchIndexes.indexOf("airlock_vec") === -1) {
  db.policy_corpus.createSearchIndex("airlock_vec", "vectorSearch", {
    fields: [
      { type: "vector", path: "embedding", numDimensions: 384, similarity: "cosine" },
      { type: "filter", path: "class" },
      { type: "filter", path: "tenant" },
      { type: "filter", path: "modality" },
      { type: "filter", path: "kind" },
    ],
  });
  ok("createSearchIndex airlock_vec (384d cosine + 4 filter paths)");
} else ok("airlock_vec exists");

if (searchIndexes.indexOf("airlock_text") === -1) {
  db.policy_corpus.createSearchIndex("airlock_text", "search", {
    mappings: {
      dynamic: false,
      fields: { text: { type: "string" }, class: { type: "token" } },
    },
  });
  ok("createSearchIndex airlock_text (lexical)");
} else ok("airlock_text exists");

// ---------------------------------------------------------------------------
// 4. THE BLOCKING POLL — R10
//
//    Do not remove this to "save time at 10:30". The failure it prevents is silent.
// ---------------------------------------------------------------------------
log("blocking until both search indexes are READY and queryable…");
const started = Date.now();
let lastPrinted = "";

while (true) {
  const status = db.policy_corpus
    .aggregate([{ $listSearchIndexes: {} }])
    .toArray()
    .map((i) => ({ name: i.name, status: i.status, queryable: i.queryable }));

  const line = status.map((s) => `${s.name}=${s.status}/${s.queryable}`).join("  ");
  if (line !== lastPrinted) {
    log(`  ${line}`);
    lastPrinted = line;
  }

  const want = ["airlock_vec", "airlock_text"];
  const ready = want.every((n) => {
    const s = status.find((x) => x.name === n);
    return s && s.status === "READY" && s.queryable === true;
  });

  if (ready) {
    ok("both search indexes READY and queryable");
    break;
  }

  const failed = status.find((s) => s.status === "FAILED");
  if (failed) {
    warn(`index ${failed.name} FAILED to build.`);
    warn("Fallback: set AIRLOCK_RRF=client so retrieval uses the client-side RRF path");
    warn("in services/inspect/mongo.py. It emits the identical score/scoreDetails shape,");
    warn("so B's UI does not change. Do NOT block the day on this.");
    break;
  }

  if (Date.now() - started > INDEX_READY_TIMEOUT_MS) {
    warn(`indexes not READY after ${INDEX_READY_TIMEOUT_MS / 1000}s.`);
    warn("Proceeding anyway — but retrieval WILL return empty until they are.");
    warn("Set AIRLOCK_RRF=client to bypass mongot entirely.");
    break;
  }
  sleep(POLL_INTERVAL_MS);
}

// ---------------------------------------------------------------------------
// 5. Summary
// ---------------------------------------------------------------------------
print("");
log("collection state:");
[
  ["policy_corpus", db.policy_corpus.countDocuments({})],
  ["decisions", db.decisions.countDocuments({})],
  ["benign_eval", db.benign_eval.countDocuments({})],
  ["inspect_metrics", db.inspect_metrics.countDocuments({})],
].forEach(([n, c]) => log(`  ${n.padEnd(16)} ${c} docs`));

print("");
ok("schema seed complete.");
log("next: python bench/seed_corpus.py   (nine clauses + ~200 bge-small exemplars)");
