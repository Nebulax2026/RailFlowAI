import { spawn } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";
const child = spawn(isWindows ? "cmd.exe" : "npm", isWindows ? ["/d", "/s", "/c", "npm.cmd run dev"] : ["run", "dev"], {
  cwd: resolve(rootDir, "frontend"),
  env: process.env,
  shell: false,
  stdio: "inherit"
});

child.on("error", (error) => {
  console.error(`Frontend failed to start: ${error.message}`);
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
