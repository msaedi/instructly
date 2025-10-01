import { execa } from "execa";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const frontendDir = resolve(here, "../frontend");

await execa("node", ["scripts/contract-check.mjs"], {
  cwd: frontendDir,
  stdio: "inherit",
});
