// End-to-end test server: a real ComfyUI with DiceForge, in a temporary base directory (--base-directory) filled with the test files, so your own
// ComfyUI folders are never touched: custom_nodes/DiceForge links to this repository's DiceForge folder, and models, wildcards, input images and
// user settings are made here. A small stand-in for Civitai answers the Model info lookups. Playwright starts this before the tests and stops it
// after them (playwright.config.js); it can also be started by hand: node server.js.
const fs = require("fs");
const http = require("http");
const path = require("path");
const { spawn } = require("child_process");
const { REPO, PORT, CIVITAI_PORT, BASE, comfyuiPath, comfyuiPython } = require("./settings");
const { MODELS, WILDCARDS, CIVITAI, png } = require("./fixtures");

function prepare() {
  fs.rmSync(BASE, { recursive: true, force: true });
  for (const folder of ["custom_nodes", "input/e2e", "output", "user/default", "models/wildcards"]) fs.mkdirSync(path.join(BASE, folder), { recursive: true });
  fs.symlinkSync(path.join(REPO, "DiceForge"), path.join(BASE, "custom_nodes", "DiceForge"), "junction"); // junction: no admin rights needed on Windows.
  for (const [file, { content }] of Object.entries(MODELS)) {
    fs.mkdirSync(path.dirname(path.join(BASE, "models", file)), { recursive: true });
    fs.writeFileSync(path.join(BASE, "models", file), content);
  }
  fs.writeFileSync(path.join(BASE, "models", "loras", "detail.preview.png"), png(8, 8, [0, 200, 0]));
  for (const [file, text] of Object.entries(WILDCARDS)) {
    fs.mkdirSync(path.dirname(path.join(BASE, "models", "wildcards", file)), { recursive: true });
    fs.writeFileSync(path.join(BASE, "models", "wildcards", file), text);
  }
  fs.writeFileSync(path.join(BASE, "input", "e2e", "red.png"), png(32, 16, [255, 0, 0]));
  fs.writeFileSync(path.join(BASE, "input", "e2e", "blue.png"), png(16, 24, [0, 0, 255]));
  fs.writeFileSync(path.join(BASE, "user", "default", "comfy.settings.json"), JSON.stringify({ "Comfy.TutorialCompleted": true }));
}

// Civitai stand-in: /by-hash/<sha256> answers like Civitai's model-versions/by-hash for the test models, /image/... serves a small image.
function startCivitai() {
  const server = http.createServer((request, response) => {
    const byHash = /^\/by-hash\/([0-9a-f]{64})$/.exec(request.url);
    if (byHash && CIVITAI[byHash[1]]) {
      response.writeHead(200, { "Content-Type": "application/json" });
      return response.end(JSON.stringify(CIVITAI[byHash[1]]));
    }
    if (request.url.startsWith("/image/")) {
      response.writeHead(200, { "Content-Type": "image/png" });
      return response.end(png(8, 8, [200, 100, 0]));
    }
    response.writeHead(404, { "Content-Type": "application/json" });
    response.end(JSON.stringify({ error: "Model not found" }));
  });
  server.listen(CIVITAI_PORT, "127.0.0.1");
  return server;
}

const comfyui = comfyuiPath();
if (!comfyui) {
  console.error("DiceForge e2e: set COMFYUI_PATH to your ComfyUI folder (the one with main.py).");
  process.exit(1);
}
prepare();
const civitai = startCivitai();
const python = comfyuiPython(comfyui);
console.log(`DiceForge e2e: ${python} ${path.join(comfyui, "main.py")} --base-directory ${BASE} --port ${PORT}`);
const child = spawn(python, ["main.py", "--cpu", "--listen", "127.0.0.1", "--port", String(PORT), "--base-directory", BASE, "--disable-auto-launch"], {
  cwd: comfyui,
  stdio: "inherit",
  env: {
    ...process.env,
    DICEFORGE_CIVITAI_URL: `http://127.0.0.1:${CIVITAI_PORT}/by-hash/{}`,
    NO_PROXY: ["127.0.0.1", "localhost", process.env.NO_PROXY].filter(Boolean).join(","),
    no_proxy: ["127.0.0.1", "localhost", process.env.no_proxy].filter(Boolean).join(","),
  },
});
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  civitai.close();
  child.kill();
  setTimeout(() => {
    fs.rmSync(BASE, { recursive: true, force: true });
    process.exit(code);
  }, 1500);
}
child.on("exit", (code) => { if (!stopping) { console.error(`DiceForge e2e: ComfyUI exited (${code}).`); stop(1); } });
for (const signal of ["SIGINT", "SIGTERM"]) process.on(signal, () => stop(0));

