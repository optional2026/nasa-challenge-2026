// Offline production build with esbuild (used where Vite cannot be installed).
// Produces the same dist/ layout the backend serves: dist/index.html + dist/assets/*.
import { build } from "esbuild";
import { mkdirSync, readFileSync, writeFileSync, rmSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = dirname(fileURLToPath(import.meta.url));
const dist = join(root, "dist");
if (existsSync(dist)) rmSync(dist, { recursive: true });
mkdirSync(join(dist, "assets"), { recursive: true });
const nodePaths = (process.env.NODE_PATH || "").split(":").filter(Boolean);
await build({
  entryPoints: [join(root, "src/main.tsx")],
  bundle: true, minify: true, format: "esm", target: "es2020", jsx: "automatic",
  outfile: join(dist, "assets/app.js"), loader: { ".css": "css" }, nodePaths,
  define: { "process.env.NODE_ENV": '"production"' }, logLevel: "info",
});
const html = readFileSync(join(root, "index.html"), "utf8")
  .replace('<script type="module" src="/src/main.tsx"></script>',
           '<link rel="stylesheet" href="/assets/app.css"><script type="module" src="/assets/app.js"></script>');
writeFileSync(join(dist, "index.html"), html);
console.log("built", dist);
