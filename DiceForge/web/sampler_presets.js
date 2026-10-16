import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { askConfirm, askText, background } from "./dom.js";
import { modelSource, fetchBases, baseOf } from "./lora_stack.js";

// Sampler presets in the right-click menu of KSampler, KSampler Advanced and any node with steps, cfg, sampler_name and scheduler: the settings
// recommended for Anima, Anima Turbo, Illustrious and NoobAI (eps and v-pred), Auto (the one for the base model of the connected checkpoint, from
// Model info, or else from its file name), and your own presets (sampler_presets.py keeps them in the ComfyUI user folder).
const FIELDS = ["steps", "cfg", "sampler_name", "scheduler"];
let presets = { builtin: [], user: [] };
async function request(path, options) {
  const response = await api.fetchApi(path, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
async function loadPresets() {
  try { presets = await request("/diceforge/sampler-presets"); } catch { /* No answer: the menu offers what it had. */ }
  return presets;
}
function toast(severity, summary, detail) {
  const toaster = app.extensionManager?.toast;
  if (toaster?.add) toaster.add({ severity, summary, detail, life: 4000 });
  else if (severity === "error") alert(`${summary}: ${detail}`);
}
const widgetsOf = (node) => Object.fromEntries(FIELDS.map((name) => [name, node.widgets?.find((widget) => widget.name === name)]));
const isSampler = (node) => Object.values(widgetsOf(node)).every(Boolean);

// Sets the node's widgets to a preset; a sampler or scheduler this ComfyUI doesn't have is left as it is. Returns the names of the ones skipped.
export function applyPreset(node, preset) {
  const skipped = [];
  for (const [name, widget] of Object.entries(widgetsOf(node))) {
    const value = preset[name];
    const values = widget.options?.values;
    if (value === undefined || (Array.isArray(values) && !values.includes(value))) {
      skipped.push(name);
      continue;
    }
    widget.value = value;
    widget.callback?.(value);
  }
  node.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
  return skipped;
}
function applyAndSay(node, preset) {
  const skipped = applyPreset(node, preset);
  const settings = `${preset.steps} steps, CFG ${preset.cfg}, ${preset.sampler_name}, ${preset.scheduler}`;
  if (skipped.length) toast("warn", `Sampler preset ${preset.name}`, `${settings}; not set (this ComfyUI doesn't have it): ${skipped.join(", ")}`);
  else toast("success", `Sampler preset ${preset.name}`, preset.note ? `${settings}. ${preset.note}` : settings);
}

// The built-in preset for a model: by its Civitai base model, else by its file name. null when it is none of these families.
export function presetNameFor(file, base) {
  const name = file.split(/[\\/]/).pop();
  const vpred = /v[-_ ]?pred/i.test(name);
  const family = (text) => {
    if (/anima/i.test(text)) return /turbo/i.test(name) ? "Anima Turbo" : "Anima";
    if (/noob/i.test(text)) return vpred ? "NoobAI (v-pred)" : "NoobAI (eps)";
    if (/illustrious|(^|[^a-z])ilxl/i.test(text)) return "Illustrious";
    return null;
  };
  return (base && family(base)) || family(name);
}
async function applyAuto(node) {
  const source = modelSource(node);
  if (!source) {
    toast("warn", "Sampler presets", "Auto needs a checkpoint or diffusion model connected to the model input.");
    return;
  }
  await fetchBases([source]);
  const base = baseOf(source.kind, source.file);
  const name = presetNameFor(source.file, base);
  const preset = presets.builtin.find((item) => item.name === name);
  if (preset) applyAndSay(node, preset);
  else toast("warn", "Sampler presets", `No preset for ${source.file.split(/[\\/]/).pop()}${base ? ` (${base})` : ""}: Anima, Illustrious and NoobAI are known.`);
}
async function saveCurrent(node) {
  const name = (await askText("Name of the new sampler preset:"))?.trim();
  if (!name) return;
  if (presets.user.some((item) => item.name.toLowerCase() === name.toLowerCase()) && !(await askConfirm(`A preset named "${name}" already exists. Replace it?`))) return;
  const widgets = widgetsOf(node);
  const body = { name, ...Object.fromEntries(FIELDS.map((field) => [field, widgets[field].value])) };
  try {
    await request("/diceforge/sampler-presets", { method: "POST", body: JSON.stringify(body) });
    toast("success", "Sampler presets", `Saved ${name}.`);
  } catch (error) {
    toast("error", "Sampler presets", error.message);
  }
  await loadPresets();
}
async function deletePreset(name) {
  if (!(await askConfirm(`Delete the sampler preset "${name}"?`))) return;
  try {
    await request(`/diceforge/sampler-presets?${new URLSearchParams({ name })}`, { method: "DELETE" });
    toast("success", "Sampler presets", `Deleted ${name}.`);
  } catch (error) {
    toast("error", "Sampler presets", error.message);
  }
  await loadPresets();
}

const describe = (preset) => `${preset.steps} steps · CFG ${preset.cfg}`; // Short, the menu is narrow; the sampler and scheduler are in the message.
const run = (promise) => promise.catch((error) => toast("error", "Sampler presets", error.message));
// The entries of the submenu (also what the tests click).
export function presetItems(node) {
  const presetItem = (preset, mark) => ({ content: `${mark} ${preset.name} · ${describe(preset)}`, callback: () => applyAndSay(node, preset) });
  return [
    { content: "✨ Auto (from the connected model)", callback: () => run(applyAuto(node)) },
    null,
    ...presets.builtin.map((preset) => presetItem(preset, "🎲")),
    ...(presets.user.length ? [null, ...presets.user.map((preset) => presetItem(preset, "★"))] : []),
    null,
    { content: "💾 Save current as preset…", callback: () => run(saveCurrent(node)) },
    ...presets.user.map((preset) => ({ content: `🗑 Delete ${preset.name}`, callback: () => run(deletePreset(preset.name)) })),
  ];
}

app.registerExtension({
  name: "DiceForge.SamplerPresets",
  setup() {
    background(loadPresets());
  },
  getNodeMenuItems(node) {
    if (!isSampler(node)) return [];
    const items = presetItems(node);
    return [{
      content: "🎲 Sampler presets",
      has_submenu: true,
      submenu: { options: items }, // Both menus (classic and Nodes 2.0) open it from here.
    }];
  },
});
