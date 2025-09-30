import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";
import openapiTS, { astToString, COMMENT_HEADER } from "openapi-typescript";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const OUT = path.resolve(__dirname, "../types/generated/api.d.ts");
const SRC = process.env.OPENAPI_SOURCE || "http://localhost:8000/openapi.json";

async function loadDoc() {
  if (SRC.startsWith("http")) {
    const res = await fetch(SRC);
    if (!res.ok) throw new Error(`fetch ${SRC} -> ${res.status}`);
    const json = await res.json();
    if (!json || typeof json !== "object" || !json.openapi) {
      throw new Error(`Invalid OpenAPI JSON from ${SRC}`);
    }
    return json;
  }

  const filePath = path.resolve(__dirname, SRC);
  const raw = await fs.readFile(filePath, "utf8");
  const json = JSON.parse(raw);
  if (!json || typeof json !== "object" || !json.openapi) {
    throw new Error(`Invalid OpenAPI JSON from ${SRC}`);
  }
  return json;
}

const doc = await loadDoc();
const ast = await openapiTS(doc, { version: 3 });
const content = COMMENT_HEADER + astToString(ast);

if (!/(?:declare|export)\s+(?:namespace|interface|type)\s+/m.test(content)) {
  console.error("Generated output does not look like TS declarations. First 200 chars:");
  console.error(content.slice(0, 200));
  process.exit(1);
}

await fs.mkdir(path.dirname(OUT), { recursive: true });
await fs.writeFile(OUT, content, "utf8");
console.log(`Wrote ${OUT} from ${SRC}`);
