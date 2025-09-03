import { execSync } from "node:child_process";
import { existsSync, mkdirSync } from "node:fs";

if (!existsSync(".artifacts")) mkdirSync(".artifacts", { recursive: true });

// Generate to a temp file then diff with the tracked file
execSync("npm run contract:export", { stdio: "inherit" });
execSync("openapi-typescript ../backend/openapi/openapi.json -o .artifacts/api.tmp.d.ts --export-type", { stdio: "inherit" });

// Exit non-zero on diff (CI fails if drift)
try {
  execSync("git diff --no-index --quiet .artifacts/api.tmp.d.ts types/generated/api.d.ts", { stdio: "inherit" });
  // eslint-disable-next-line no-console
  console.log("✅ Contract check passed (no drift).");
} catch {
  // eslint-disable-next-line no-console
  console.error("❌ Contract drift detected. Run: npm run contract:pull");
  process.exit(1);
}
