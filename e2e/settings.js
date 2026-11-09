// Settings shared by the end-to-end server (server.js), the Playwright config and the tests.
const os = require("os");
const path = require("path");
const fs = require("fs");

const REPO = path.resolve(__dirname, "..");
// One ComfyUI per worker of the tests, each on its own port (the Civitai stand-in takes the next one) and in its own folder. The slot of a
// server is DICEFORGE_E2E_SLOT (playwright.config.js starts one per worker, slot n for worker n); a test takes its worker's slot instead
// (helpers.js), so the tests never read this module's slot.
const WORKERS = Math.max(1, Number(process.env.DICEFORGE_E2E_WORKERS || 1));
const SLOT = Number(process.env.DICEFORGE_E2E_SLOT || 0);
const portOf = (slot) => Number(process.env.DICEFORGE_E2E_PORT || 8199) + 2 * slot;
const urlOf = (slot) => `http://127.0.0.1:${portOf(slot)}`;
// A slot's base folder (ComfyUI's --base-directory) sits in the slot's own folder, so a test can write beside it (robustness.spec.js)
// without touching another slot's.
const baseOf = (slot) => path.join(process.env.DICEFORGE_E2E_BASE || path.join(os.tmpdir(), "diceforge-e2e"), `slot-${slot}`, "base");
const PORT = portOf(SLOT);
const CIVITAI_PORT = PORT + 1; // The stand-in for Civitai (server.js), so the tests never go online.
const BASE = baseOf(SLOT);
const URL = urlOf(SLOT);

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

module.exports = { REPO, WORKERS, SLOT, PORT, CIVITAI_PORT, BASE, URL, portOf, urlOf, baseOf, comfyuiPath, comfyuiPython };
