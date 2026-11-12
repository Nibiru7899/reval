// Regenerates the typed API client input: `reval api-schema` -> openapi.json -> src/api/schema.d.ts.
// Never hand-edit schema.d.ts; run `npm run gen:api` after any change to the API's response models.
import { execFileSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const web = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const repo = resolve(web, "..");
const venv = process.platform === "win32" ? join(repo, ".venv", "Scripts", "reval.exe") : join(repo, ".venv", "bin", "reval");
const reval = existsSync(venv) ? venv : "reval";
const schema = join(web, "openapi.json");

execFileSync(reval, ["api-schema", "--out", schema], { cwd: repo, stdio: "inherit" });
execFileSync(process.execPath, [join(web, "node_modules", "openapi-typescript", "bin", "cli.js"), schema, "-o", join(web, "src", "api", "schema.d.ts")], {
  cwd: web,
  stdio: "inherit",
});
