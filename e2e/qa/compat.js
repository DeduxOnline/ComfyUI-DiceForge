// The comparison of an old workflow with what this version makes of it (e2e/compat.spec.js, the compat agent): the corpus of saved workflows
// (e2e/workflows/<version>.json, made by e2e/qa/snapshot.js), loading one in the page, and what it lost or changed.
//   node e2e/qa/compat.js [<version>]       every saved workflow (or one) against the running e2e server, in both designs; exits with 1 on a change
const fs = require("fs");
const path = require("path");

const FOLDER = path.join(__dirname, "..", "workflows");
// The saved workflows, oldest version first: one per published release, none before the first.
const corpus = () => (fs.existsSync(FOLDER) ? fs.readdirSync(FOLDER) : []).filter((name) => name.endsWith(".json"))
  .sort((a, b) => a.localeCompare(b, undefined, { numeric: true })).map((name) => JSON.parse(fs.readFileSync(path.join(FOLDER, name), "utf8")));
const asJson = (value) => {
  if (typeof value !== "string" || !/^\s*[[{]/.test(value)) return undefined;
  try { return JSON.parse(value); } catch { return undefined; }
};
// Is what was saved still there in what this version has? Numbers within rounding, JSON text read as JSON, and of objects only the keys that
// were saved (new ones are fine).
function kept(saved, now) {
  if (typeof saved === "number" && typeof now === "number") return Math.abs(saved - now) < 1e-9;
  const json = asJson(saved);
  if (json !== undefined) return kept(json, asJson(now) ?? now);
  if (Array.isArray(saved)) return Array.isArray(now) && saved.length === now.length && saved.every((item, index) => kept(item, now[index]));
  if (saved && typeof saved === "object") return !!now && typeof now === "object" && Object.keys(saved).every((key) => kept(saved[key], now[key]));
  return saved === now;
}
const show = (value) => JSON.stringify(value)?.slice(0, 120);

function widgetChanges(saved, now) {
  const changes = [];
  for (const [id, { type, widgets }] of Object.entries(saved.widgets)) {
    const node = now.widgets[id];
    if (!now.types.includes(type)) changes.push(`${type}: the node type doesn't exist any more`);
    else if (!node) changes.push(`node ${id} (${type}) is gone`);
    else {
      for (const [name, value] of Object.entries(widgets)) {
        if (!(name in node.widgets)) changes.push(`${type}.${name}: no such widget any more (it was ${show(value)})`);
        else if (!kept(value, node.widgets[name])) changes.push(`${type}.${name}: ${show(value)} became ${show(node.widgets[name])}`);
      }
    }
  }
  return changes;
}

function promptChanges(saved, now) {
  const changes = [];
  for (const [id, { class_type: type, inputs }] of Object.entries(saved.prompt)) {
    const node = now.prompt[id];
    if (!node) continue; // Said by widgetChanges.
    if (node.class_type !== type) changes.push(`prompt node ${id}: ${type} became ${node.class_type}`);
    for (const [name, value] of Object.entries(inputs)) {
      if (!(name in node.inputs)) changes.push(`prompt ${type}.${name}: not sent any more (it was ${show(value)})`);
      else if (!kept(value, node.inputs[name])) changes.push(`prompt ${type}.${name}: ${show(value)} became ${show(node.inputs[name])}`);
    }
  }
  return changes;
}

// In the page: the saved workflow loaded, and what this version makes of it.
async function load(page, workflow) {
  return page.evaluate(async (workflow) => {
    const { app, LiteGraph } = window;
    app.graph.clear();
    await app.loadGraphData(workflow);
    const keptWidget = (widget) => widget.serialize !== false && widget.options?.serialize !== false;
    return {
      types: Object.keys(LiteGraph.registered_node_types),
      widgets: Object.fromEntries(app.graph.nodes.map((node) => [node.id, { type: node.type,
        widgets: Object.fromEntries((node.widgets ?? []).filter(keptWidget).map((widget) => [widget.name, widget.value])) }])),
      prompt: (await app.graphToPrompt()).output,
    };
  }, workflow);
}

module.exports = { corpus, kept, widgetChanges, promptChanges, load };

if (require.main === module) {
  const { open } = require("./lib");
  (async () => {
    const only = process.argv[2];
    let changes = 0;
    for (const vue of [true, false]) {
      const { browser, page, errors } = await open({ vue });
      for (const saved of corpus().filter((item) => !only || item.diceforge === only)) {
        const now = await load(page, saved.workflow);
        const found = [...widgetChanges(saved, now), ...promptChanges(saved, now)];
        changes += found.length;
        const what = found.length ? ["", ...found].join("\n  ") : "kept everything";
        console.log(`${vue ? "Nodes 2.0" : "classic"} · DiceForge ${saved.diceforge}: ${what}`);
      }
      if (errors.length) console.log(`page errors:\n  ${errors.join("\n  ")}`);
      changes += errors.length;
      await browser.close();
    }
    process.exitCode = changes ? 1 : 0;
  })().catch((error) => {
    console.error(error);
    process.exitCode = 2;
  });
}
