import fs from "fs";
import http from "http";
import path from "path";
import { fileURLToPath } from "url";
import { spawn } from "child_process";
import { createServer } from "vite";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const frontendRoot = path.resolve(__dirname, "..");
const repoRoot = path.resolve(frontendRoot, "..");
const esbuildPath = path.resolve(repoRoot, "tools", "esbuild.exe");

if (process.platform === "win32" && !process.env.ESBUILD_BINARY_PATH && fs.existsSync(esbuildPath)) {
  process.env.ESBUILD_BINARY_PATH = esbuildPath;
}

const devPort = Number(process.env.VITE_DEV_PORT || 5173);

async function startVite() {
  const server = await createServer({
    root: frontendRoot,
    configFile: path.resolve(frontendRoot, "vite.config.js"),
    server: {
      host: "127.0.0.1",
      port: devPort,
    },
  });
  await server.listen();
  server.printUrls();
  await new Promise(() => {});
}

function runCommand(command, args, cwd) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { cwd, stdio: "inherit" });
    child.on("error", reject);
    child.on("close", (code) => {
      if (code === 0) {
        resolve();
      } else {
        reject(new Error(`${command} exited with code ${code}`));
      }
    });
  });
}

async function buildFallbackAssets(outputDir) {
  fs.mkdirSync(outputDir, { recursive: true });
  const bundlePath = path.join(outputDir, "dev.bundle.js");
  const cssPath = path.join(outputDir, "dev.css");

  const esbuildCmd = process.platform === "win32"
    ? esbuildPath
    : "npx";
  const esbuildArgs = process.platform === "win32"
    ? [
      "./src/main.tsx",
      "--bundle",
      "--format=esm",
      "--sourcemap=inline",
      `--outfile=${bundlePath}`,
      "--tsconfig=tsconfig.json",
      "--loader:.ts=ts",
      "--loader:.tsx=tsx",
      "--define:process.env.NODE_ENV=\"development\"",
    ]
    : [
      "esbuild",
      "./src/main.tsx",
      "--bundle",
      "--format=esm",
      "--sourcemap=inline",
      `--outfile=${bundlePath}`,
      "--tsconfig=tsconfig.json",
      "--loader:.ts=ts",
      "--loader:.tsx=tsx",
      "--define:process.env.NODE_ENV=\"development\"",
    ];

  await runCommand(esbuildCmd, esbuildArgs, frontendRoot);

  const tailwindCmd = process.platform === "win32"
    ? path.join(frontendRoot, "node_modules", ".bin", "tailwindcss.cmd")
    : path.join(frontendRoot, "node_modules", ".bin", "tailwindcss");
  const tailwindArgs = [
    "-i",
    path.join(frontendRoot, "src", "index.css"),
    "-o",
    cssPath,
    "--config",
    path.join(frontendRoot, "tailwind.config.ts"),
  ];

  await runCommand(tailwindCmd, tailwindArgs, frontendRoot);
}

async function startFallback() {
  const outputDir = path.join(frontendRoot, ".fallback");
  await buildFallbackAssets(outputDir);

  const indexHtml = fs.readFileSync(path.join(frontendRoot, "index.html"), "utf8");
  const envScript = `<script>window.__APP_ENV__=${JSON.stringify({
    VITE_API_BASE_URL: "http://127.0.0.1:8099",
    VITE_BACKEND_URL: "http://127.0.0.1:8099",
    DEV: false,
    MODE: "development",
  })};</script>`;
  const patchedIndex = indexHtml.replace(
    '<script type="module" src="/src/main.tsx"></script>',
    `${envScript}<link rel="stylesheet" href="/dev.css" /><script type="module" src="/dev.bundle.js"></script>`,
  );

  const server = http.createServer((req, res) => {
    const url = req.url || "/";
    if (url === "/" || url === "/index.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(patchedIndex);
      return;
    }
    if (url === "/dev.bundle.js") {
      res.writeHead(200, { "Content-Type": "application/javascript; charset=utf-8" });
      res.end(fs.readFileSync(path.join(outputDir, "dev.bundle.js")));
      return;
    }
    if (url === "/dev.css") {
      res.writeHead(200, { "Content-Type": "text/css; charset=utf-8" });
      res.end(fs.readFileSync(path.join(outputDir, "dev.css")));
      return;
    }
    res.writeHead(404);
    res.end("Not found");
  });

  server.listen(devPort, "127.0.0.1", () => {
    console.log(`Fallback dev server running at http://127.0.0.1:${devPort}`);
  });
  await new Promise(() => {});
}

try {
  await startVite();
} catch (error) {
  const message = error?.message || "";
  if (message.includes("spawn EPERM")) {
    console.warn("Vite failed due to spawn EPERM. Starting fallback dev server...");
    await startFallback();
  } else {
    throw error;
  }
}
