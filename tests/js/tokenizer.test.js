"use strict";
// The page's word splitting against SQLite FTS5's, for every unit in the published corpus. The
// expected counts and hashes are in tests/fixtures/search-tokens.json, which the build script
// dumped from the real index, so this needs no database and runs in CI.

const test = require("node:test");
const assert = require("node:assert/strict");
const crypto = require("node:crypto");
const fs = require("node:fs");
const path = require("node:path");

const root = path.join(__dirname, "..", "..");
const { tokenize } = require(path.join(root, "docs", "demo", "search-core.js"));
const corpus = JSON.parse(fs.readFileSync(path.join(root, "docs", "demo", "corpus.json"), "utf8"));
const expected = JSON.parse(
  fs.readFileSync(path.join(root, "tests", "fixtures", "search-tokens.json"), "utf8")
);

test("the corpus and the token fixture list the same units", () => {
  const ids = corpus.units.map((unit) => unit.id);
  assert.deepEqual([...ids].sort(), Object.keys(expected).sort());
});

test("the page finds the same words as FTS5 in every unit", () => {
  for (const unit of corpus.units) {
    const words = tokenize(unit.header + "\n" + unit.body, corpus.fold);
    const [count, hash] = expected[unit.id];
    assert.equal(words.length, count, unit.id + " word count");
    const found = crypto.createHash("sha256").update(words.join("\n"), "utf8").digest("hex");
    assert.equal(found, hash, unit.id + " words");
  }
});

test("a few plain cases", () => {
  const none = {};
  assert.deepEqual(tokenize("GHSA-p6xc-xr62-6r2g", none), ["ghsa", "p6xc", "xr62", "6r2g"]);
  assert.deepEqual(tokenize("  lodash@4.17.21, ", none), ["lodash", "4", "17", "21"]);
  assert.deepEqual(tokenize("", none), []);
  assert.deepEqual(tokenize("café", { "é": "e" }), ["cafe"]);
  assert.deepEqual(tokenize("áb", { "́": "" }), ["ab"]);
  assert.deepEqual(tokenize("́", { "́": "" }), []);
});
