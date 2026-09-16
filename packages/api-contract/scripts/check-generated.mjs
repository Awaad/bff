#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { GENERATED_HEADER, generateContractFromFile } from "./generator.mjs";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(packageRoot, "../..");

const schemaPath = path.resolve(
  process.env.BFF_OPENAPI_SCHEMA ?? path.join(repositoryRoot, "artifacts/openapi/control-api.json"),
);
const generatedPath = path.resolve(
  process.env.BFF_OPENAPI_TYPES ?? path.join(packageRoot, "src/generated/openapi.d.ts"),
);

async function requireFile(file, description) {
  try {
    await fs.access(file);
  } catch (error) {
    throw new Error(`${description} not found at ${file}`, { cause: error });
  }
}

await requireFile(schemaPath, "canonical OpenAPI schema");
await requireFile(generatedPath, "generated OpenAPI contract");

const generated = await fs.readFile(generatedPath, "utf8");
const expected = await generateContractFromFile(schemaPath);

if (generated !== expected) {
  throw new Error(
    "generated OpenAPI types are stale; run `pnpm contract:generate` and commit the result",
  );
}

if (!generated.startsWith(GENERATED_HEADER)) {
  throw new Error("generated OpenAPI contract is missing its generated-file header");
}

console.log("generated OpenAPI types match the canonical schema");
