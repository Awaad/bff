import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
import openapiTS, { astToString } from "openapi-typescript";

const pkg = JSON.parse(fs.readFileSync(new URL("../package.json", import.meta.url), "utf8"));

test("contract generator is isolated on TypeScript 5", () => {
  assert.match(pkg.devDependencies.typescript, /^5\./);
});

test("openapi-typescript stays on the peer-compatible generator package", () => {
  assert.equal(pkg.devDependencies["openapi-typescript"], "7.13.0");
});

test("openapi-typescript can generate a minimal contract in this workspace", async () => {
  const ast = await openapiTS({
    openapi: "3.1.0",
    info: { title: "contract-smoke", version: "0.0.0" },
    paths: {
      "/health": {
        get: {
          responses: {
            200: {
              description: "healthy",
              content: {
                "application/json": {
                  schema: {
                    type: "object",
                    properties: { ok: { type: "boolean" } },
                    required: ["ok"],
                  },
                },
              },
            },
          },
        },
      },
    },
  });

  const output = astToString(ast);
  assert.match(output, /\/health/);
  assert.match(output, /ok/);
});
