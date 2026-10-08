// Where the ComfyUI frontend internals DiceForge relies on (e2e/contract.spec.js) are in a ComfyUI's frontend build: the comfyui-frontend-package
// of its Python. For the comfy-watcher agent, to compare two ComfyUI versions before running anything: a marker found in one and not in the
// other, or with other numbers, is where to look.
//   node e2e/qa/internals.js                 (the ComfyUI of the e2e tests: COMFYUI_PATH, COMFYUI_PYTHON, or ../ComfyUI)
//   node e2e/qa/internals.js --json          (the same as JSON, to diff two runs)
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const { comfyuiPath, comfyuiPython } = require("../settings");

// What to look for, and what DiceForge needs from it.
const MARKERS = [
  ["DOM widget default margin", /DEFAULT_MARGIN=(\d+)/g, "10: dom.js fitToContent makes a panel 2 × margin taller"],
  ["DOM widget layout size", /computeLayoutSize\(/g, "fitToContent removes it from its widgets"],
  ["classic arrange: computeSize + 4", /computeSize\(\)\[1\]\+4/g, "a widget with computeSize gets that height + 4"],
  ["classic DOM box: computedHeight - 4", /computedHeight-4/g, "a DOM widget's box is computedHeight - 2 × margin"],
  ["Nodes 2.0 rows of layout widgets grow", /hasLayoutSize/g, "why fitToContent removes computeLayoutSize"],
  ["Nodes 2.0 node body", /node-body-/g, "e2e/qa/lib.js measure"],
  ["Nodes 2.0 widget row", /"node-widget"|`node-widget`/g, "e2e/qa/lib.js measure"],
  ["Nodes 2.0 advanced inputs button", /advanced-inputs-button/g, "the e2e tests"],
  ["Show advanced inputs", /Show advanced inputs/g, "the e2e tests"],
  ["node.showAdvanced", /showAdvanced/g, "prompt_preview.js"],
  ["Nodes 2.0 setting", /Comfy\.VueNodes\.Enabled/g, "node_size.js, prompt_preview.js"],
  ["getNodeMenuItems hook", /getNodeMenuItems/g, "the node menus of DiceForge"],
  ["beforeConfigureGraph hook", /beforeConfigureGraph/g, "prompt_preview.js"],
  ["execution_cached event", /execution_cached/g, "dice_grid.js, prompt_preview.js"],
];

function frontend() {
  const comfyui = comfyuiPath();
  if (!comfyui) throw new Error("No ComfyUI: set COMFYUI_PATH (or run e2e/qa/setup.sh)");
  const python = comfyuiPython(comfyui);
  const [folder, version] = execFileSync(python, ["-c",
    "import comfyui_frontend_package as f, importlib.metadata as m, os; print(os.path.dirname(f.__file__)); print(m.version('comfyui-frontend-package'))"],
  { encoding: "utf8" }).trim().split("\n");
  return { comfyui, version, assets: path.join(folder, "static", "assets") };
}

function look() {
  const { comfyui, version, assets } = frontend();
  const files = fs.readdirSync(assets).filter((name) => name.endsWith(".js")).map((name) => [name, fs.readFileSync(path.join(assets, name), "utf8")]);
  const markers = MARKERS.map(([name, pattern, why]) => {
    const found = files.flatMap(([file, text]) => [...text.matchAll(pattern)].map((match) => ({ file, at: match.index, text, match })));
    const first = found[0];
    const around = first ? first.text.slice(Math.max(0, first.at - 60), first.at + first.match[0].length + 60).replace(/\s+/g, " ") : "";
    return { name, why, count: found.length, values: [...new Set(found.map((item) => item.match[1]).filter(Boolean))], file: first?.file ?? "", around };
  });
  return { comfyui, frontend: version, markers };
}

const result = look();
if (process.argv.includes("--json")) {
  console.log(JSON.stringify(result, null, 2));
} else {
  console.log(`ComfyUI ${result.comfyui}, frontend ${result.frontend}`);
  for (const marker of result.markers) {
    const values = marker.values.length ? ` = ${marker.values.join(", ")}` : "";
    console.log(`${marker.count ? "found  " : "MISSING"} ${marker.name}${values} (${marker.count}×) · ${marker.why}`);
    if (marker.count) console.log(`        ${marker.file}: …${marker.around}…`);
  }
}
