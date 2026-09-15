import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const isWindows = process.platform === "win32";
const backendDir = resolve(rootDir, "backend");
const venvPython = resolve(backendDir, ".venv", isWindows ? "Scripts/python.exe" : "bin/python");
const command = existsSync(venvPython) ? venvPython : (isWindows ? "py" : "python3");
const child = spawn(command, ["-m", "uvicorn", "app.main:app", "--reload"], {
  cwd: backendDir,
  env: process.env,
  shell: false,
  stdio: "inherit"
});

child.on("error", (error) => {
  console.error(`Backend failed to start: ${error.message}`);
  process.exitCode = 1;
});
child.on("exit", (code) => {
  process.exitCode = code ?? 1;
});
