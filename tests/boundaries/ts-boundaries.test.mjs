import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  checkRepository,
  extractModuleSpecifiers,
} from "../../scripts/check_ts_boundaries.mjs";

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "bff-ts-boundaries-"));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));

  return {
    root,
    write(relativePath, content) {
      const target = path.join(root, relativePath);
      fs.mkdirSync(path.dirname(target), { recursive: true });
      fs.writeFileSync(target, content, "utf8");
    },
    package(relativeDir, name) {
      this.write(
        `${relativeDir}/package.json`,
        JSON.stringify({ name, private: true }),
      );
    },
  };
}

test("lexer detects TypeScript static, type-only, re-export, and dynamic imports", async () => {
  const specifiers = await extractModuleSpecifiers(`
    import type { Contract } from "@bff/contracts";
    import { runtime } from "@bff/runtime";
    export type { Shared } from "@bff/shared";
    export * from "@bff/public-api";
    await import("@bff/lazy");
  `);

  assert.deepEqual(
    specifiers.map(({ specifier }) => specifier),
    [
      "@bff/contracts",
      "@bff/runtime",
      "@bff/shared",
      "@bff/public-api",
      "@bff/lazy",
    ],
  );
});

test("allows apps to depend on shared packages", async (t) => {
  const repo = fixture(t);
  repo.package("apps/runtime", "@bff/runtime");
  repo.package("packages/contracts", "@bff/contracts");
  repo.write("apps/runtime/src/index.ts", 'import "@bff/contracts";\n');

  assert.deepEqual(await checkRepository(repo.root), []);
});

test("blocks packages importing apps", async (t) => {
  const repo = fixture(t);
  repo.package("apps/runtime", "@bff/runtime");
  repo.package("packages/execution-engine", "@bff/execution-engine");
  repo.write(
    "packages/execution-engine/src/index.ts",
    'import "@bff/runtime";\n',
  );

  const violations = await checkRepository(repo.root);

  assert.equal(violations.length, 1);
  assert.match(violations[0], /packages code must not import apps code/);
});

test("blocks workers importing apps", async (t) => {
  const repo = fixture(t);
  repo.package("apps/control-api", "@bff/control-api");
  repo.package("workers/outbox", "@bff/outbox-worker");
  repo.write("workers/outbox/src/index.ts", 'import "@bff/control-api";\n');

  const violations = await checkRepository(repo.root);

  assert.equal(violations.length, 1);
  assert.match(violations[0], /workers code must not import apps code/);
});

test("blocks relative imports that cross from package into app", async (t) => {
  const repo = fixture(t);
  repo.write(
    "packages/contracts/src/index.ts",
    'export * from "../../../apps/runtime/src/index";\n',
  );
  repo.write("apps/runtime/src/index.ts", "export const runtime = true;\n");

  const violations = await checkRepository(repo.root);

  assert.equal(violations.length, 1);
  assert.match(violations[0], /packages code must not import apps code/);
});

test("blocks dynamic imports that cross from worker into app", async (t) => {
  const repo = fixture(t);
  repo.package("apps/runtime", "@bff/runtime");
  repo.package("workers/outbox", "@bff/outbox-worker");
  repo.write(
    "workers/outbox/src/index.ts",
    'await import("@bff/runtime");\n',
  );

  const violations = await checkRepository(repo.root);

  assert.equal(violations.length, 1);
  assert.match(violations[0], /workers code must not import apps code/);
});

test("blocks type-only imports across forbidden package boundaries", async (t) => {
  const repo = fixture(t);
  repo.package("apps/runtime", "@bff/runtime");
  repo.package("packages/contracts", "@bff/contracts");
  repo.write(
    "packages/contracts/src/index.ts",
    'import type { Runtime } from "@bff/runtime";\n',
  );

  const violations = await checkRepository(repo.root);

  assert.equal(violations.length, 1);
  assert.match(violations[0], /packages code must not import apps code/);
});
