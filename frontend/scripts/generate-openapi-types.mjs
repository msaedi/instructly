import { execSync } from "node:child_process";
import fs from "node:fs/promises";
import path from "node:path";
import process from "node:process";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const OUT = path.resolve(__dirname, "../types/generated/api.d.ts");
const SRC = process.env.OPENAPI_SOURCE || "http://localhost:8000/openapi.json";

async function loadDoc() {
  const isHttp = SRC.startsWith("http");
  if (isHttp) {
    const res = await fetch(SRC);
    if (!res.ok) throw new Error(`fetch ${SRC} -> ${res.status}`);
    const json = await res.json();
    if (!json || typeof json !== "object" || !json.openapi) {
      throw new Error(`Invalid OpenAPI JSON from ${SRC}`);
    }
    return { source: SRC };
  }

  const filePath = path.resolve(process.cwd(), SRC);
  const raw = await fs.readFile(filePath, "utf8");
  const json = JSON.parse(raw);
  if (!json || typeof json !== "object" || !json.openapi) {
    throw new Error(`Invalid OpenAPI JSON from ${SRC}`);
  }
  return { source: filePath };
}

const { source } = await loadDoc();
const cli = path.resolve(process.cwd(), "node_modules/.bin/openapi-typescript" + (process.platform === "win32" ? ".cmd" : ""));
execSync(`${JSON.stringify(cli)} ${JSON.stringify(source)} -o ${JSON.stringify(OUT)} --export-type`, {
  stdio: "inherit",
  env: process.env,
});

const content = await fs.readFile(OUT, "utf8");
if (!/(?:declare|export)\s+(?:namespace|interface|type)\s+/m.test(content)) {
  console.error("Generated output does not look like TS declarations. First 200 chars:");
  console.error(content.slice(0, 200));
  process.exit(1);
}

console.log(`Wrote ${OUT} from ${source}`);
