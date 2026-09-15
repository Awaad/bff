import assert from "node:assert/strict";
import fs from "node:fs/promises";
import test from "node:test";

import {
  GENERATED_HEADER,
  generateContractFromFile,
  generateContractFromSchema,
} from "../scripts/generator.mjs";

const fixture = new URL("./fixtures/minimal.openapi.json", import.meta.url);
const snapshot = new URL("./snapshots/minimal.openapi.d.ts", import.meta.url);

test("generator output is deterministic", async () => {
  const first = await generateContractFromFile(fixture);
  const second = await generateContractFromFile(fixture);

  assert.equal(first, second);
  assert.ok(first.startsWith(GENERATED_HEADER));
});

test("generator output matches the committed regression snapshot", async () => {
  const actual = await generateContractFromFile(fixture);
  const expected = await fs.readFile(snapshot, "utf8");

  assert.equal(actual, expected);
});

test("generator rejects non-OpenAPI input before code generation", async () => {
  await assert.rejects(
    () =>
      generateContractFromSchema({
        info: { title: "not-openapi", version: "0.0.0" },
        paths: {},
      }),
    /OpenAPI schema must declare an OpenAPI 3\.x version/,
  );
});

test("generator requires paths to be an object", async () => {
  await assert.rejects(
    () =>
      generateContractFromSchema({
        openapi: "3.1.0",
        info: { title: "invalid", version: "0.0.0" },
        paths: null,
      }),
    /paths object/,
  );
});
