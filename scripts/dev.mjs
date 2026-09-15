import { spawn } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const isWindows = process.platform === "win32";
const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = resolve(rootDir, "backend");
const venvPython = resolve(backendDir, ".venv", isWindows ? "Scripts/python.exe" : "bin/python");
const pythonCommand = existsSync(venvPython) ? venvPython : (isWindows ? "py" : "python3");

const processes = [
  {
    name: "backend",
    command: pythonCommand,
    args: ["-m", "uvicorn", "app.main:app", "--reload"],
    cwd: backendDir
  },
  {
    name: "frontend",
    command: isWindows ? "cmd.exe" : "npm",
    args: isWindows ? ["/d", "/s", "/c", "npm.cmd run dev"] : ["run", "dev"],
    cwd: resolve(rootDir, "frontend")
  }
];

let shuttingDown = false;
const children = [];

function prefixOutput(name, stream, chunk) {
  const lines = chunk.toString().split(/\r?\n/);
  for (const line of lines) {
    if (line.length > 0) {
      stream.write(`[${name}] ${line}\n`);
    }
  }
}

function stopAll(signal = "SIGTERM") {
  if (shuttingDown) {
    return;
  }

  shuttingDown = true;
  for (const child of children) {
    if (!child.killed) {
      child.kill(signal);
    }
  }
}

for (const processConfig of processes) {
  const child = spawn(processConfig.command, processConfig.args, {
    cwd: processConfig.cwd,
    env: process.env,
    shell: false
  });

  children.push(child);

  child.stdout.on("data", (chunk) => prefixOutput(processConfig.name, process.stdout, chunk));
  child.stderr.on("data", (chunk) => prefixOutput(processConfig.name, process.stderr, chunk));

  child.on("error", (error) => {
    console.error(`[${processConfig.name}] failed to start: ${error.message}`);
    stopAll();
    process.exitCode = 1;
  });

  child.on("exit", (code, signal) => {
    if (shuttingDown) {
      return;
    }

    const reason = signal ? `signal ${signal}` : `code ${code}`;
    console.error(`[${processConfig.name}] exited with ${reason}`);
    stopAll();
    process.exitCode = code ?? 1;
  });
}

process.on("SIGINT", () => stopAll("SIGINT"));
process.on("SIGTERM", () => stopAll("SIGTERM"));
