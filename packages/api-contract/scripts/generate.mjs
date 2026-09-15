import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import openapiTS, { astToString } from "openapi-typescript";

const root = process.cwd();
const schemaPath = process.env.BFF_OPENAPI_SCHEMA ?? path.join(root, "openapi.json");
const outputPath = path.join(root, "src/generated/openapi.d.ts");

const raw = await fs.readFile(schemaPath, "utf8");
const schema = JSON.parse(raw);
const ast = await openapiTS(schema);
const output = `${astToString(ast)}\n`;

await fs.mkdir(path.dirname(outputPath), { recursive: true });
await fs.writeFile(outputPath, output, "utf8");
console.log(`generated ${path.relative(root, outputPath)} from ${path.relative(root, schemaPath)}`);
