import { spawn, spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const isWindows = process.platform === "win32";
const rootDir = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = resolve(rootDir, "backend");
const venvPython = resolve(backendDir, ".venv", isWindows ? "Scripts/python.exe" : "bin/python");
const frontendDir = resolve(rootDir, "frontend");

function runSetup(command, args, cwd) {
  const result = spawnSync(command, args, { cwd, env: process.env, stdio: "inherit", shell: false });
  if (result.error || result.status !== 0) {
    console.error(`Setup failed: ${command} ${args.join(" ")}`);
    if (result.error) console.error(result.error.message);
    process.exit(result.status || 1);
  }
}

if (!existsSync(venvPython)) {
  const python = isWindows ? "py" : "python3.12";
  console.log(`[setup] Creating backend virtual environment with ${python}...`);
  runSetup(python, ["-m", "venv", ".venv"], backendDir);
}
if (spawnSync(venvPython, ["-m", "uvicorn", "--version"], { stdio: "ignore" }).status !== 0) {
  console.log("[setup] Installing backend dependencies...");
  runSetup(venvPython, ["-m", "pip", "install", "-r", "requirements.txt"], backendDir);
}
if (!existsSync(resolve(frontendDir, "node_modules", "next"))) {
  console.log("[setup] Installing frontend dependencies...");
  runSetup(isWindows ? "npm.cmd" : "npm", ["ci"], frontendDir);
}

const processes = [
  {
    name: "backend",
    command: venvPython,
    args: ["-m", "uvicorn", "app.main:app", "--reload"],
    cwd: backendDir
  },
  {
    name: "frontend",
    command: isWindows ? "cmd.exe" : "npm",
    args: isWindows ? ["/d", "/s", "/c", "npm.cmd run dev"] : ["run", "dev"],
    cwd: frontendDir
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
