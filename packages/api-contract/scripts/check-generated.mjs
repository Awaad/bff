import fs from "node:fs/promises";

const file = new URL("../src/generated/openapi.d.ts", import.meta.url);
const text = await fs.readFile(file, "utf8");
if (!text.trim()) {
  throw new Error("generated OpenAPI contract is empty");
}
