// Settings shared by the end-to-end server (server.js), the Playwright config and the tests.
const os = require("os");
const path = require("path");
const fs = require("fs");

const REPO = path.resolve(__dirname, "..");
const PORT = Number(process.env.DICEFORGE_E2E_PORT || 8199);
const CIVITAI_PORT = PORT + 1; // The stand-in for Civitai (server.js), so the tests never go online.
const BASE = process.env.DICEFORGE_E2E_BASE || path.join(os.tmpdir(), "diceforge-e2e"); // ComfyUI's --base-directory for the tests.
const URL = `http://127.0.0.1:${PORT}`;

// The ComfyUI to test with: COMFYUI_PATH, or a ComfyUI folder next to this repository.
function comfyuiPath() {
  const candidates = [process.env.COMFYUI_PATH, path.join(REPO, "..", "ComfyUI")].filter(Boolean);
  return candidates.map((folder) => path.resolve(folder)).find((folder) => fs.existsSync(path.join(folder, "main.py")));
}

// The Python that runs it: COMFYUI_PYTHON, else a virtual environment of that ComfyUI (venv or .venv, inside or next to it, or the portable
// build's python_embeded), else python3 / python from the PATH.
function comfyuiPython(comfyui) {
  if (process.env.COMFYUI_PYTHON) return process.env.COMFYUI_PYTHON;
  const windows = process.platform === "win32";
  const inVenv = (folder) => path.join(folder, windows ? "Scripts" : "bin", windows ? "python.exe" : "python");
  const candidates = [
    inVenv(path.join(comfyui, "venv")), inVenv(path.join(comfyui, ".venv")),
    inVenv(path.join(comfyui, "..", "venv")), inVenv(path.join(comfyui, "..", ".venv")),
    path.join(comfyui, "..", "python_embeded", "python.exe"),
  ];
  return candidates.find((file) => fs.existsSync(file)) || (windows ? "python" : "python3");
}

module.exports = { REPO, PORT, CIVITAI_PORT, BASE, URL, comfyuiPath, comfyuiPython };
