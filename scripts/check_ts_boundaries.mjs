#!/usr/bin/env node

import fs from "node:fs";
import path from "node:path";
import process from "node:process";
import { pathToFileURL } from "node:url";
import { init, parse } from "es-module-lexer";

const SOURCE_EXTENSIONS = new Set([".js", ".jsx", ".mjs", ".mts", ".ts", ".tsx"]);
const SOURCE_ROOTS = ["apps", "packages", "workers"];

function normalize(value) {
  return value.split(path.sep).join("/");
}

function classify(relativePath) {
  const normalized = normalize(relativePath);
  if (normalized === "packages" || normalized.startsWith("packages/")) return "packages";
  if (normalized === "workers" || normalized.startsWith("workers/")) return "workers";
  if (normalized === "apps" || normalized.startsWith("apps/")) return "apps";
  return "other";
}

function walkFiles(root) {
  const files = [];

  for (const sourceRoot of SOURCE_ROOTS) {
    const absoluteRoot = path.join(root, sourceRoot);
    if (!fs.existsSync(absoluteRoot)) continue;

    const stack = [absoluteRoot];
    while (stack.length > 0) {
      const current = stack.pop();

      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        if (entry.name === "node_modules" || entry.name === "dist" || entry.name === ".turbo") {
          continue;
        }

        const absolute = path.join(current, entry.name);
        if (entry.isDirectory()) {
          stack.push(absolute);
        } else if (entry.isFile() && SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
          files.push(absolute);
        }
      }
    }
  }

  return files.sort();
}

function workspacePackages(root) {
  const packages = new Map();

  for (const sourceRoot of SOURCE_ROOTS) {
    const absoluteRoot = path.join(root, sourceRoot);
    if (!fs.existsSync(absoluteRoot)) continue;

    const stack = [absoluteRoot];
    while (stack.length > 0) {
      const current = stack.pop();

      for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
        if (!entry.isDirectory() || entry.name === "node_modules") continue;

        const absolute = path.join(current, entry.name);
        const manifestPath = path.join(absolute, "package.json");

        if (fs.existsSync(manifestPath)) {
          const manifest = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
          if (typeof manifest.name === "string" && manifest.name.length > 0) {
            packages.set(manifest.name, path.relative(root, absolute));
          }
        }

        stack.push(absolute);
      }
    }
  }

  return packages;
}

function targetForSpecifier(root, sourcePath, specifier, packageMap) {
  if (specifier.startsWith(".")) {
    return path.relative(root, path.resolve(path.dirname(sourcePath), specifier));
  }

  const exact = packageMap.get(specifier);
  if (exact) return exact;

  for (const [packageName, packageRoot] of packageMap.entries()) {
    if (specifier.startsWith(`${packageName}/`)) return packageRoot;
  }

  return null;
}

function boundaryViolation(fromClass, toClass) {
  if (fromClass === "packages" && (toClass === "apps" || toClass === "workers")) {
    return true;
  }

  if (fromClass === "workers" && toClass === "apps") {
    return true;
  }

  return false;
}

function lineAndColumn(source, offset) {
  const prefix = source.slice(0, Math.max(0, offset));
  const lines = prefix.split("\n");
  return {
    line: lines.length,
    column: lines.at(-1).length + 1,
  };
}

function importSpecifier(record) {
  // es-module-lexer 3.x full build exposes descriptive accessors, while the
  // compact legacy aliases remain useful for compatibility. Supporting both
  // makes this checker resilient across compatible lexer patch/minor releases.
  return record.specifier ?? record.n;
}

function importOffset(record) {
  return record.specifierStart ?? record.s ?? record.importStart ?? record.ss ?? 0;
}

export async function extractModuleSpecifiers(source, sourceName = "@") {
  await init();
  const [imports] = parse(source, sourceName);

  return imports
    .map((record) => ({
      specifier: importSpecifier(record),
      offset: importOffset(record),
    }))
    .filter((record) => typeof record.specifier === "string");
}

export async function checkRepository(root) {
  await init();

  const packageMap = workspacePackages(root);
  const violations = [];

  for (const sourcePath of walkFiles(root)) {
    const relativeSource = path.relative(root, sourcePath);
    const sourceClass = classify(relativeSource);
    const contents = fs.readFileSync(sourcePath, "utf8");

    let imports;
    try {
      imports = await extractModuleSpecifiers(contents, sourcePath);
    } catch (error) {
      throw new Error(
        `failed to analyze module imports in ${normalize(relativeSource)}: ${error.message}`,
        { cause: error },
      );
    }

    for (const imported of imports) {
      const target = targetForSpecifier(root, sourcePath, imported.specifier, packageMap);
      if (target === null) continue;

      const targetClass = classify(target);
      if (!boundaryViolation(sourceClass, targetClass)) continue;

      const { line, column } = lineAndColumn(contents, imported.offset);
      violations.push(
        `${normalize(relativeSource)}:${line}:${column}: ` +
          `${sourceClass} code must not import ${targetClass} code (${imported.specifier})`,
      );
    }
  }

  return violations.sort();
}

async function main() {
  const root = path.resolve(process.argv[2] ?? path.join(import.meta.dirname, ".."));
  const violations = await checkRepository(root);

  if (violations.length === 0) return 0;

  for (const violation of violations) {
    console.error(violation);
  }

  console.error(`architecture boundary check failed: ${violations.length} violation(s)`);
  return 1;
}

const invokedPath = process.argv[1] ? pathToFileURL(path.resolve(process.argv[1])).href : null;

if (invokedPath === import.meta.url) {
  process.exitCode = await main();
}
