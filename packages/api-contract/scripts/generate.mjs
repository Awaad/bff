#!/usr/bin/env node

import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

import { generateContractFromFile } from "./generator.mjs";

const packageRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const repositoryRoot = path.resolve(packageRoot, "../..");

const schemaPath = path.resolve(
  process.env.BFF_OPENAPI_SCHEMA ?? path.join(repositoryRoot, "artifacts/openapi/control-api.json"),
);
const outputPath = path.resolve(
  process.env.BFF_OPENAPI_TYPES ?? path.join(packageRoot, "src/generated/openapi.d.ts"),
);

try {
  await fs.access(schemaPath);
} catch (error) {
  throw new Error(
    `canonical OpenAPI schema not found at ${schemaPath}; ` +
      "export the control API schema before generating TypeScript contracts",
    { cause: error },
  );
}

const output = await generateContractFromFile(schemaPath);
await fs.mkdir(path.dirname(outputPath), { recursive: true });

const temporaryPath = `${outputPath}.tmp-${process.pid}`;

try {
  await fs.writeFile(temporaryPath, output, "utf8");
  await fs.rename(temporaryPath, outputPath);
} finally {
  await fs.rm(temporaryPath, { force: true });
}

console.log(
  `generated ${path.relative(repositoryRoot, outputPath)} ` +
    `from ${path.relative(repositoryRoot, schemaPath)}`,
);
