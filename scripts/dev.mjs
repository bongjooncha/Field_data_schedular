import { spawn } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const venvPython = path.join(root, ".venv", "Scripts", "python.exe");
const python = fs.existsSync(venvPython) ? venvPython : "python";

function run(command, cwd) {
  return spawn(command, {
    cwd,
    stdio: "inherit",
    shell: true,
    windowsHide: false,
  });
}

console.log("화면  http://127.0.0.1:5173");
console.log("서버  http://127.0.0.1:8765");

const api = run(
  `"${python}" -m uvicorn backend.app:app --host 127.0.0.1 --port 8765 --reload`,
  root,
);
const ui = run("npm run dev:ui", path.join(root, "frontend"));

let exiting = false;

function shutdown(code = 0) {
  if (exiting) return;
  exiting = true;
  for (const child of [api, ui]) {
    if (!child.pid) continue;
    if (process.platform === "win32") {
      spawn("taskkill", ["/pid", String(child.pid), "/t", "/f"], { shell: true, windowsHide: true });
    } else {
      child.kill("SIGTERM");
    }
  }
  setTimeout(() => process.exit(code), 400);
}

api.on("exit", (code) => {
  if (!exiting) shutdown(code ?? 1);
});
ui.on("exit", (code) => {
  if (!exiting) shutdown(code ?? 1);
});

process.on("SIGINT", () => shutdown(0));
process.on("SIGTERM", () => shutdown(0));
