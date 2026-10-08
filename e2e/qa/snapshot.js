// A workflow of a DiceForge version, kept so later versions are tested against it (e2e/compat.spec.js): every DiceForge node the running server
// has, with every widget set to a value that is not its default, saved as the page saves it, loaded again, and saved with what the page sends
// the server for it (the prompt). Make one from each release, with that release's DiceForge on the e2e server:
//   node e2e/qa/snapshot.js --version 1.1.0 [--out e2e/workflows/1.1.0.json]
// Needs the e2e server running (e2e/qa/serve.sh start) and writes e2e/workflows/<version>.json, which goes into git.
const fs = require("fs");
const path = require("path");
const { open } = require("./lib");

const option = (name, fallback) => {
  const at = process.argv.indexOf(`--${name}`);
  return at > 0 ? process.argv[at + 1] : fallback;
};
const projectVersion = () => /^version\s*=\s*"([^"]+)"/m.exec(fs.readFileSync(path.join(__dirname, "..", "..", "pyproject.toml"), "utf8"))[1];
const version = option("version", projectVersion());
const out = option("out", path.join(__dirname, "..", "workflows", `${version}.json`));

// In the page: every DiceForge node, each widget changed from its default (numbers up a step, the next choice, booleans flipped, text written),
// the seeds' "control after generate" fixed so a run doesn't change them, and LoRA Stack given rows.
function build() {
  const { app, LiteGraph } = window;
  const kept = (widget) => widget.serialize !== false && widget.options?.serialize !== false; // Not the panels (previews, the LoRA list).
  app.graph.clear();
  const types = Object.entries(LiteGraph.registered_node_types).filter(([, type]) => /DiceForge/i.test(type.nodeData?.python_module ?? "")).map(([name]) => name).sort();
  const choices = (widget) => {
    const values = widget.options?.values;
    return typeof values === "function" ? values() : values ?? [];
  };
  const changedValue = (widget) => {
    const value = widget.value;
    if (widget.name === "control_after_generate") return "fixed";
    if (typeof value === "boolean") return !value;
    if (widget.type === "combo") return choices(widget).find((item) => item !== value) ?? value;
    if (typeof value === "number") {
      const step = widget.options?.round || (widget.options?.step2 ?? 1);
      const max = widget.options?.max ?? Infinity, min = widget.options?.min ?? -Infinity;
      return value + step <= max ? value + step : Math.max(min, value - step);
    }
    if (typeof value === "string" && !widget.hidden) return `compat ${widget.name} кот`;
    return value;
  };
  types.forEach((type, index) => {
    const node = LiteGraph.createNode(type);
    node.pos = [40 + (index % 5) * 520, 40 + Math.floor(index / 5) * 800];
    app.graph.add(node);
    for (const widget of node.widgets ?? []) {
      if (!kept(widget)) continue;
      const value = type === "DiceForgeLoraStack" && widget.name === "loras"
        ? JSON.stringify({ rows: [{ lora: "style/ink.safetensors", strength: 0.8, on: true }, { lora: "detail.safetensors", strength: 0.5, on: false }], groups: {}, separate_clip: false })
        : changedValue(widget);
      widget.value = value;
      widget.callback?.(value);
    }
  });
  return types;
}

// In the page: each node's widgets by name (what a later version must find under the same names).
function widgetsByName() {
  const kept = (widget) => widget.serialize !== false && widget.options?.serialize !== false;
  return Object.fromEntries(window.app.graph.nodes.map((node) => [node.id, { type: node.type,
    widgets: Object.fromEntries((node.widgets ?? []).filter(kept).map((widget) => [widget.name, widget.value])) }]));
}

(async () => {
  const { browser, page, errors } = await open({ vue: false });
  const types = await page.evaluate(build);
  await page.waitForTimeout(800);
  const saved = await page.evaluate(() => window.app.graph.serialize());
  await page.evaluate(async (workflow) => { // Loaded again: what is kept is what the page keeps.
    window.app.graph.clear();
    await window.app.loadGraphData(workflow);
  }, saved);
  await page.waitForTimeout(800);
  const workflow = await page.evaluate(() => window.app.graph.serialize());
  const widgets = await page.evaluate(widgetsByName);
  const prompt = await page.evaluate(async () => (await window.app.graphToPrompt()).output);
  const comfyui = await page.evaluate(async () => (await (await fetch("/system_stats")).json()).system?.comfyui_version ?? "");
  fs.mkdirSync(path.dirname(out), { recursive: true });
  fs.writeFileSync(out, `${JSON.stringify({ diceforge: version, comfyui, made: new Date().toISOString().slice(0, 10), types, widgets, prompt, workflow }, null, 1)}\n`);
  console.log(`${types.length} node types of DiceForge ${version} (ComfyUI ${comfyui}) -> ${out}`);
  if (errors.length) console.log(`Page errors:\n  ${errors.join("\n  ")}`);
  await browser.close();
  process.exitCode = errors.length ? 1 : 0;
})().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});
