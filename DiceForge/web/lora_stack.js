import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openModelInfo } from "./model_info.js";
import { openModelBrowser, BROWSERS, compareBases } from "./model_browser.js";
import { fitNodeHeight } from "./node_size.js";
import { addStyleOnce, askConfirm, asking, askText, background, element, fitToContent } from "./dom.js";

// LoRA Stack (lora_stack.py): the rows of LoRAs drawn in the node, like rgthree's Power Lora Loader. The node's "loras" text input holds them as JSON;
// it is hidden and this panel edits it. Each row: on/off, the LoRA (click to change it in the LoRA Browser), Model info, a group, a fixed strength or
// a random range (🎲), and the CLIP strength when it is set apart. Groups (A-D) take turns: "use 1 to 2 of these". A row made for another base model
// than the connected model is marked, and the stack can be saved as a preset file and applied in any LoRA Stack.
const NODE_TYPE = "DiceForgeLoraStack";
const GROUPS = ["A", "B", "C", "D"];
const LORAS = BROWSERS.find((spec) => spec.kind === "loras");
const EMPTY = { rows: [], groups: {}, separate_clip: false };
// The stack as the panel edits it, whatever the saved JSON holds (a workflow edited by hand or damaged), like lora_stack.parse_stack on the server:
// rows are objects with a LoRA name, trigger words a list (text with commas is split), groups objects of min and max.
const isObject = (value) => value !== null && typeof value === "object" && !Array.isArray(value);
function cleanStack(stack) {
  stack = isObject(stack) ? stack : {};
  const rows = (Array.isArray(stack.rows) ? stack.rows : []).filter((row) => isObject(row) && typeof row.lora === "string" && row.lora).map((row) => {
    const words = typeof row.trigger_words === "string" ? row.trigger_words.split(",") : Array.isArray(row.trigger_words) ? row.trigger_words : [];
    return { ...row, group: typeof row.group === "string" ? row.group : "",
      trigger_words: words.filter((word) => typeof word === "string" || typeof word === "number").map((word) => String(word).trim()).filter(Boolean) };
  });
  const groups = Object.fromEntries(Object.entries(isObject(stack.groups) ? stack.groups : {}).filter(([, settings]) => isObject(settings)));
  return { ...stack, rows, groups, separate_clip: !!stack.separate_clip };
}

const STYLE = `
.dfls{display:flex;flex-direction:column;gap:4px;font:12px system-ui,sans-serif;color:#ddd;width:100%;box-sizing:border-box;padding:2px 0}
.dfls .row{display:flex;overflow:hidden;align-items:center;gap:4px;background:#1f1f1f;border:1px solid #444;border-radius:14px;padding:2px 6px;min-height:24px}
.dfls .row.off{opacity:.5}.dfls .row.missing{border-color:#a55}.dfls .row.drag{border-color:#6a9ad8}
.dfls .grip{cursor:grab;color:#777;user-select:none;padding:0 2px}
.dfls .name{flex:1;min-width:40px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;cursor:pointer}.dfls .name:hover{color:#fff;text-decoration:underline}
.dfls input[type=number]::-webkit-inner-spin-button,.dfls input[type=number]::-webkit-outer-spin-button{-webkit-appearance:none;margin:0}
.dfls input[type=number]{-moz-appearance:textfield;text-align:center;width:40px;flex:none;background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:1px 3px;font:inherit}
.dfls button,.dfls select,.dfls input[type=checkbox],.dfls .grip{flex:none}.dfls select{background:#262626;color:#eee;border:1px solid #555;border-radius:4px;font:inherit;padding:0 1px}
.dfls button{background:#262626;color:#ddd;border:1px solid #555;border-radius:4px;padding:0 5px;font:inherit;cursor:pointer;line-height:18px}.dfls button:hover{background:#333}
.dfls button.on{background:#3a5a8a;border-color:#6a9ad8;color:#fff}.dfls .muted{color:#999}
.dfls .add{border-radius:6px;padding:4px;width:100%}.dfls .foot{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.dfls .group{display:flex;gap:4px;align-items:center;padding:1px 6px;color:#bbb}.dfls .tag{font-weight:700;color:#cfe0ff}
.dfls input[type=checkbox]{margin:0;cursor:pointer}
.dfls button.none{opacity:.45;text-decoration:line-through}
.dflt{position:fixed;z-index:10001;background:#262626;border:1px solid #555;border-radius:8px;box-shadow:0 6px 20px #000a;font:13px system-ui,sans-serif;color:#ddd;padding:8px 10px;width:280px;max-height:60vh;overflow:auto;display:flex;flex-direction:column;gap:6px}
.dflt b{color:#fff}.dflt label{display:flex;gap:6px;align-items:center;cursor:pointer}.dflt .src{color:#888;font-size:11px;margin-left:auto}
.dflt input[type=text]{background:#1e1e1e;color:#eee;border:1px solid #555;border-radius:4px;padding:3px 6px;font:inherit;flex:1;min-width:0}
.dflt .line{display:flex;gap:6px;align-items:center}.dflt button{background:#222;color:#eee;border:1px solid #666;border-radius:5px;padding:2px 8px;cursor:pointer;font:inherit}
.dflt button.on{background:#3a5a8a;border-color:#6a9ad8}.dflt .muted{color:#999;font-size:12px}
.dfls .row.warn{border-color:#c9a13a}.dfls .row.bad{border-color:#d9534f}.dfls .mark{flex:none;cursor:help}.dfls .model,.dfls .note{padding:0 4px}
.dflp-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dflp{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(720px,94vw);max-height:84vh;display:flex;flex-direction:column;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dflp h2{margin:0 0 10px;font-size:20px;color:#fff}.dflp .top{display:flex;gap:8px;margin-bottom:10px;align-items:center}
.dflp .list{overflow:auto;display:flex;flex-direction:column;gap:6px}.dflp .item{display:flex;gap:8px;align-items:center;background:#2a2a2a;border:1px solid #474747;border-radius:6px;padding:6px 8px}
.dflp .item .text{flex:1;min-width:0}.dflp .item b{color:#fff}.dflp .muted{color:#999;font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dflp button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit}.dflp button:hover{background:#2c2c2c}
.dflp button.go{border-color:#4a7a4a;color:#bfe8bf}.dflp .status{color:#9c9;font-size:13px;min-height:18px;margin-top:8px}
`;
const addStyle = () => addStyleOnce("dfls-style", STYLE);
const shortName = (file) => file.split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
const round = (value) => Math.round(value * 100) / 100;

let loraFiles = null; // The files of the loras folders, to mark rows whose file is missing.
async function loraList() {
  if (!loraFiles) {
    try { loraFiles = new Set(await (await api.fetchApi("/models/loras")).json()); } catch { loraFiles = new Set(); }
  }
  return loraFiles;
}

// Base model check: Civitai's base model of each LoRA against the one of the model the stack gets (traced back through the nodes in between to the
// loader, like Load Checkpoint or Load Diffusion Model). Different families (SDXL / SD 1.5 / Flux...) do not work together; within a family (SDXL,
// Pony, Illustrious, NoobAI) a LoRA often works on another base's model, but not as well. Unknown bases give no warning. The comparison itself
// (family, compareBases) is in model_browser.js, which also uses it for the "Fits the model" filter.
const MODEL_WIDGETS = [[/ckpt|checkpoint/i, "checkpoints"], [/unet|diffusion/i, "diffusion_models"]];
const MODEL_FILE = /\.(safetensors|ckpt|pt|pth|bin|gguf|sft)$/i;
function modelSource(node) {
  const seen = new Set();
  for (let current = node; current && !seen.has(current.id);) {
    seen.add(current.id);
    const slot = current.inputs?.findIndex((input) => input.type === "MODEL") ?? -1;
    const source = slot >= 0 ? current.getInputNode(slot) : null;
    if (!source) return null;
    for (const [pattern, kind] of MODEL_WIDGETS) {
      const widget = source.widgets?.find((widget) => pattern.test(widget.name) && typeof widget.value === "string" && MODEL_FILE.test(widget.value));
      if (widget) return { kind, file: widget.value };
    }
    current = source; // A node in between (another LoRA loader, Model Sampling...): follow its model input.
  }
  return null;
}
const bases = new Map(); // "kind|file" -> { base, time }: what Model info knows, asked again after a while when unknown (it may have been looked up since).
async function fetchBases(items) {
  const now = Date.now();
  const missing = items.filter(({ kind, file }) => { const known = bases.get(`${kind}|${file}`); return !known || (!known.base && now - known.time > 15000); });
  if (!missing.length) return;
  missing.forEach(({ kind, file }) => bases.set(`${kind}|${file}`, { base: bases.get(`${kind}|${file}`)?.base ?? null, time: now }));
  try {
    const response = await api.fetchApi("/diceforge/model-bases", { method: "POST", body: JSON.stringify({ items: missing }) });
    const found = (await response.json()).bases;
    missing.forEach(({ kind, file }, index) => bases.set(`${kind}|${file}`, { base: found[index] ?? null, time: now }));
  } catch { /* No answer: no warnings. */ }
}
const baseOf = (kind, file) => bases.get(`${kind}|${file}`)?.base ?? null;

// Presets: saved stacks, as files in ComfyUI/user/DiceForge/lora_presets. Replace puts a preset's rows in the node, + Add adds them to its rows;
// ⬇ File downloads the preset file (to share it), Import reads one.
async function presetRequest(path, options) {
  const response = await api.fetchApi(path, options);
  if (!response.ok) throw Object.assign(new Error(await response.text()), { status: response.status });
  return response.json();
}
async function savePreset(name, stack) {
  const body = (overwrite) => ({ method: "POST", body: JSON.stringify({ name, stack, overwrite }) });
  try {
    return await presetRequest("/diceforge/lora-presets", body(false));
  } catch (error) {
    if (error.status !== 409 || !(await askConfirm(`A preset named "${name}" already exists. Replace it?`))) throw error;
    return presetRequest("/diceforge/lora-presets", body(true));
  }
}
function openPresets(apply) {
  const back = element("div", { class: "dflp-back" });
  const list = element("div", { class: "list" });
  const status = element("div", { class: "status" });
  const say = (text) => { status.textContent = text; };
  const onKey = (event) => { if (asking()) return; if (event.key === "Escape") { event.stopPropagation(); close(); } };
  function close() { back.remove(); document.removeEventListener("keydown", onKey, true); }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  const load = (name) => presetRequest(`/diceforge/lora-presets/file?name=${encodeURIComponent(name)}`);
  async function draw() {
    let data;
    try { data = await presetRequest("/diceforge/lora-presets"); } catch (error) { return say(error.message); }
    list.replaceChildren(...(data.presets.length ? data.presets.map((preset) => element("div", { class: "item" },
      element("div", { class: "text" }, element("b", {}, preset.name), element("div", { class: "muted", title: preset.loras.join("\n") },
        `${preset.loras.length} LoRA${preset.loras.length === 1 ? "" : "s"}: ${preset.loras.map(shortName).join(", ")}`)),
      element("button", { class: "go", title: "Put this preset's rows in the node, instead of its rows", onclick: async () => { apply((await load(preset.name)).stack, "replace"); close(); } }, "Replace"),
      element("button", { title: "Add this preset's rows after the node's rows", onclick: async () => { apply((await load(preset.name)).stack, "add"); close(); } }, "+ Add"),
      element("button", { title: "Download the preset file, to share it or keep a copy", onclick: async () => {
        const blob = new Blob([JSON.stringify({ type: "DiceForge LoRA Stack preset", version: 1, stack: (await load(preset.name)).stack }, null, 1)], { type: "application/json" });
        const link = element("a", { href: URL.createObjectURL(blob), download: `${preset.name}.json` });
        document.body.append(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(link.href), 1000);
      } }, "⬇ File"),
      element("button", { title: "Delete this preset", onclick: async () => {
        if (!(await askConfirm(`Delete the preset "${preset.name}"?`))) return;
        await presetRequest(`/diceforge/lora-presets?name=${encodeURIComponent(preset.name)}`, { method: "DELETE" });
        say(`Deleted ${preset.name}.`);
        background(draw());
      } }, "🗑"))) : [element("div", { class: "muted" }, `No presets yet: save a stack with 💾 Save preset in the node, or import a preset file. They are kept in ${data.folder}.`)]));
  }
  const picker = element("input", { type: "file", accept: ".json,application/json", multiple: "", style: "display:none" });
  picker.addEventListener("change", async () => {
    for (const file of picker.files) {
      try {
        const stack = JSON.parse(await file.text());
        const name = file.name.replace(/\.json$/i, "").replace(/[^\w\-. ()]/g, "_");
        await savePreset(name, stack.stack ?? stack);
        say(`Imported ${name}.`);
      } catch (error) {
        say(`${file.name}: ${error.message}`);
      }
    }
    picker.value = "";
    background(draw());
  });
  back.append(element("div", { class: "dflp" },
    element("h2", {}, "LoRA Stack presets"),
    element("div", { class: "top" }, element("button", { onclick: () => picker.click() }, "⬆ Import file…"), picker, element("span", { style: "flex:1" }), element("button", { onclick: close }, "Close")),
    list, status));
  document.body.append(back);
  background(draw());
}

// Trigger words of a row (🏷): which of the LoRA's trigger words go to the triggers output. Default: all of them (yours from Model info, else
// Civitai's); None; or the words ticked in the list, plus your own, kept in the row (mode "custom", so presets keep them too).
async function knownTriggers(lora) {
  try {
    const response = await api.fetchApi("/diceforge/lora-triggers", { method: "POST", body: JSON.stringify({ loras: [lora] }) });
    return (await response.json()).triggers[0];
  } catch {
    return { user: [], civitai: [] };
  }
}
let openList = null;
async function openTriggers(anchor, row, save) {
  openList?.close();
  const known = await knownTriggers(row.lora);
  const defaults = known.user.length ? known.user : known.civitai;
  let mode = row.triggers || "all";
  let picked = mode === "custom" ? [...(row.trigger_words ?? [])] : mode === "none" ? [] : [...defaults];
  const extra = () => picked.filter((word) => !known.user.includes(word) && !known.civitai.includes(word));
  const box = element("div", { class: "dflt" });
  const close = () => { box.remove(); document.removeEventListener("pointerdown", outside, true); document.removeEventListener("keydown", onKey, true); openList = null; };
  const outside = (event) => { if (!box.contains(event.target) && event.target !== anchor) close(); };
  const onKey = (event) => { if (asking()) return; if (event.key === "Escape") { event.stopPropagation(); close(); } };
  const apply = (nextMode) => { mode = nextMode; save(mode, mode === "custom" ? picked : []); draw(); };
  function draw() {
    const words = [...new Set([...known.user, ...known.civitai, ...extra()])];
    const source = (word) => (known.user.includes(word) ? "yours" : known.civitai.includes(word) ? "Civitai" : "added");
    const input = element("input", { type: "text", placeholder: "Your own words, comma separated" });
    const addWords = () => {
      const added = input.value.split(",").map((word) => word.trim()).filter((word) => word && !picked.includes(word));
      if (!added.length) return;
      picked.push(...added);
      apply("custom");
    };
    input.addEventListener("keydown", (event) => { event.stopPropagation(); if (event.key === "Enter") addWords(); });
    box.replaceChildren(
      element("b", {}, `Trigger words: ${shortName(row.lora)}`),
      ...(words.length ? words.map((word) => {
        const check = element("input", { type: "checkbox" });
        check.checked = picked.includes(word);
        check.addEventListener("change", () => {
          picked = check.checked ? [...picked, word] : picked.filter((item) => item !== word);
          apply("custom");
        });
        return element("label", { title: word }, check, word, element("span", { class: "src" }, source(word)));
      }) : [element("div", { class: "muted" }, "No trigger words known: look the LoRA up on Civitai (🛈 Info or the LoRA Browser), or add your own below.")]),
      element("div", { class: "line" }, input, element("button", { onclick: addWords }, "Add")),
      element("div", { class: "line" },
        element("button", { class: mode === "all" ? "on" : "", title: "All the LoRA's trigger words (yours from Model info, else Civitai's)", onclick: () => { picked = [...defaults]; apply("all"); } }, "Default"),
        element("button", { class: mode === "none" ? "on" : "", title: "No trigger words from this LoRA", onclick: () => { picked = []; apply("none"); } }, "None"),
        element("span", { style: "flex:1" }),
        element("button", { onclick: close }, "Close")),
      element("div", { class: "muted" }, mode === "all" ? "Default: follows the LoRA's trigger words, also when they change." : mode === "none" ? "None: this LoRA adds no words." : `Custom: ${picked.length} word${picked.length === 1 ? "" : "s"}.`));
  }
  draw();
  document.body.append(box);
  const rect = anchor.getBoundingClientRect();
  Object.assign(box.style, { left: `${Math.max(8, Math.min(rect.left, innerWidth - 300))}px`, top: `${Math.min(rect.bottom + 4, innerHeight - box.offsetHeight - 8)}px` });
  document.addEventListener("pointerdown", outside, true); // pointerdown: the canvas cancels mousedown.
  document.addEventListener("keydown", onKey, true);
  openList = { close };
}

function numberInput(value, title, onChange) {
  const input = element("input", { type: "number", step: "0.05", title });
  input.value = round(value).toFixed(2);
  input.addEventListener("change", () => onChange(Number(input.value) || 0));
  input.addEventListener("wheel", (event) => { // Wheel over the field: ± 0.05, like rgthree's arrows.
    event.preventDefault();
    event.stopPropagation();
    input.value = round((Number(input.value) || 0) + (event.deltaY < 0 ? 0.05 : -0.05)).toFixed(2);
    onChange(Number(input.value));
  }, { passive: false });
  return input;
}

function setUp(node) {
  const data = node.widgets?.find((widget) => widget.name === "loras");
  if (!data || node.diceforgeStack) return;
  addStyle();
  data.hidden = true; // The JSON stays the node's value (saved and sent to the server); the panel below edits it.
  const panel = element("div", { class: "dfls" });
  // Keys typed in the panel's fields must not reach the canvas shortcuts (Escape still closes dialogs).
  panel.addEventListener("keydown", (event) => { if (event.key !== "Escape" && /^(INPUT|SELECT)$/.test(event.target.tagName)) event.stopPropagation(); });
  const widget = fitToContent(node.addDOMWidget("lora_stack", "diceforge_lora_stack", panel, { serialize: false }), panel);
  widget.serialize = false;
  const read = () => {
    try { return cleanStack(JSON.parse(data.value || "{}")); } catch { return structuredClone(EMPTY); }
  };
  const write = (stack) => {
    data.value = JSON.stringify(stack);
    data.callback?.(data.value);
    background(render());
    node.setDirtyCanvas?.(true, true);
  };
  const update = (change) => { const stack = read(); change(stack); write(stack); };
  const connectedBase = () => { const source = modelSource(node); return source ? baseOf(source.kind, source.file) : null; };
  const browse = (target) => openModelBrowser(node, LORAS, { ...target, base: connectedBase() }); // The browser starts on the LoRAs that fit the model.
  let dragged = null;

  async function render() {
    const stack = read();
    const files = await loraList();
    const rows = stack.rows.map((row, index) => {
      const set = (change) => update((next) => change(next.rows[index]));
      const missing = files.size && !files.has(row.lora);
      const strength = row.random
        ? [numberInput(row.min ?? row.strength ?? 1, "Lowest strength", (value) => set((r) => { r.min = value; })), element("span", { class: "muted" }, "–"),
           numberInput(row.max ?? row.strength ?? 1, "Highest strength", (value) => set((r) => { r.max = value; }))]
        : [numberInput(row.strength ?? 1, stack.separate_clip ? "Model strength" : "Strength (model and CLIP)", (value) => set((r) => { r.strength = value; }))];
      const clip = stack.separate_clip ? [element("span", { class: "muted", title: "CLIP strength" }, "C"), numberInput(row.clip ?? 1, "CLIP strength", (value) => set((r) => { r.clip = value; }))] : [];
      const toggle = element("input", { type: "checkbox", title: "On / off" });
      toggle.checked = row.on !== false;
      toggle.addEventListener("change", () => set((r) => { r.on = toggle.checked; }));
      const group = element("select", { title: "Group: the LoRAs of a group take turns (set how many to use below)" },
        element("option", { value: "" }, "–"), ...GROUPS.map((name) => element("option", { value: name }, name)));
      group.value = row.group || "";
      group.addEventListener("change", () => update((next) => {
        next.rows[index].group = group.value;
        if (group.value && !next.groups[group.value]) next.groups[group.value] = { min: 1, max: 1 };
      }));
      const line = element("div", { class: "row" + (row.on === false ? " off" : "") + (missing ? " missing" : ""), title: missing ? `${row.lora} is not in the loras folders` : "", "data-lora": row.lora },
        element("span", { class: "grip", title: "Drag to reorder" }, "⋮⋮"),
        toggle,
        element("span", { class: "name", title: `${row.lora}\nClick to pick another LoRA`, onclick: () => browse({
          label: "Choose", hint: `Choose puts a LoRA in this row (instead of ${shortName(row.lora)}).`,
          pick: (file) => { set((r) => { r.lora = file; }); return true; },
        }) }, shortName(row.lora)),
        element("span", { class: "mark" }),
        element("button", { title: "Model info", onclick: () => openModelInfo("loras", row.lora) }, "ℹ"),
        element("button", {
          class: row.triggers === "none" ? "none" : row.triggers === "custom" ? "on" : "",
          title: row.triggers === "none" ? "Trigger words: none" : row.triggers === "custom" ? `Trigger words: ${(row.trigger_words ?? []).join(", ") || "none picked"}` : "Trigger words: the LoRA's own (click to pick)",
          onclick: (event) => openTriggers(event.currentTarget, row, (mode, words) => set((r) => { r.triggers = mode; r.trigger_words = words; })),
        }, row.triggers === "custom" ? `🏷${(row.trigger_words ?? []).length}` : "🏷"),
        group,
        element("button", { class: row.random ? "on" : "", title: "Random strength: picked between two values by the seed mode", onclick: () => set((r) => {
          r.random = !r.random;
          if (r.random && r.min == null) { r.min = round((r.strength ?? 1) * 0.6); r.max = r.strength ?? 1; }
        }) }, "🎲"),
        ...strength, ...clip,
        element("button", { title: "Remove", onclick: () => update((next) => { next.rows.splice(index, 1); }) }, "✕"));
      // Drag and drop by the grip to reorder.
      const grip = line.querySelector(".grip");
      grip.draggable = true;
      grip.addEventListener("dragstart", (event) => { dragged = index; event.dataTransfer.effectAllowed = "move"; event.stopPropagation(); });
      line.addEventListener("dragover", (event) => { if (dragged != null) { event.preventDefault(); line.classList.add("drag"); } });
      line.addEventListener("dragleave", () => line.classList.remove("drag"));
      line.addEventListener("drop", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const from = dragged;
        dragged = null;
        if (from == null || from === index) return render();
        update((next) => { const [moved] = next.rows.splice(from, 1); next.rows.splice(index, 0, moved); });
      });
      return line;
    });
    const groups = GROUPS.filter((name) => stack.rows.some((row) => row.group === name)).map((name) => {
      const members = stack.rows.filter((row) => row.group === name && row.on !== false).length;
      const settings = stack.groups[name] ?? { min: 1, max: 1 };
      const count = (key, title) => {
        const input = element("input", { type: "number", min: "0", max: String(members), step: "1", title });
        input.value = settings[key] ?? 1;
        input.addEventListener("change", () => update((next) => {
          const value = Math.max(0, Math.round(Number(input.value) || 0));
          next.groups[name] = { min: 1, max: 1, ...next.groups[name], [key]: value };
          if (key === "min" && next.groups[name].max < value) next.groups[name].max = value;
          if (key === "max" && next.groups[name].min > value) next.groups[name].min = value;
        }));
        return input;
      };
      return element("div", { class: "group", title: "Every set of LoRAs of the group is one option of the seed mode: with deck or shuffle all of them come before any repeats" },
        element("span", { class: "tag" }, `Group ${name}:`), "use", count("min", "At least"), "to", count("max", "At most"), `of ${members}`);
    });
    const separate = element("input", { type: "checkbox" });
    separate.checked = !!stack.separate_clip;
    separate.addEventListener("change", () => update((next) => { next.separate_clip = separate.checked; }));
    panel.replaceChildren(
      ...rows,
      ...(rows.length ? [] : [element("div", { class: "muted" }, "No LoRAs yet.")]),
      ...groups,
      element("button", { class: "add", onclick: () => browse({
        label: "+ Add", multi: true, hint: "+ Add adds a LoRA to the stack; add as many as you like (or pick several with Ctrl+click and add them all), then close.",
        pick: (file) => { update((next) => { next.rows.push({ on: true, lora: file, strength: 1, clip: 1, random: false, group: "" }); }); return `${shortName(file)} added to the stack.`; },
      }) }, "＋ Add LoRA"),
      element("div", { class: "foot" },
        element("label", { class: "foot muted" }, separate, "Separate CLIP strength"),
        element("span", { style: "flex:1" }),
        element("button", { title: "Save the rows as a preset file, to apply in any LoRA Stack", onclick: async () => {
          const name = (await askText("Preset name:", ""));
          if (!name) return;
          try { await savePreset(name.trim(), read()); note(`Saved the preset ${name.trim()}.`); } catch (error) { note(error.message); }
        } }, "💾 Save preset"),
        element("button", { title: "Apply, export, import or delete presets", onclick: () => openPresets((preset, how) => update((next) => {
          if (how === "replace") Object.assign(next, { rows: preset.rows, groups: preset.groups ?? {}, separate_clip: !!preset.separate_clip });
          else {
            next.rows.push(...preset.rows);
            next.groups = { ...(preset.groups ?? {}), ...next.groups };
            next.separate_clip = next.separate_clip || !!preset.separate_clip;
          }
        })) }, "📂 Presets")),
      modelLine, noteLine);
    background(checkBases());
    if (!node.flags?.collapsed) fitNodeHeight(node); // Room for the rows (node_size.js).
  }
  const modelLine = element("div", { class: "muted model" });
  const noteLine = element("div", { class: "muted note" });
  let noteTimer = null;
  const note = (text) => { noteLine.textContent = text; clearTimeout(noteTimer); noteTimer = setTimeout(() => { noteLine.textContent = ""; }, 5000); };
  // Marks rows made for another base model than the connected model's; runs after each render and every few seconds (the model can change upstream).
  async function checkBases() {
    if (!panel.isConnected) return;
    const source = modelSource(node);
    await fetchBases([...(source ? [source] : []), ...read().rows.map((row) => ({ kind: "loras", file: row.lora }))]);
    const modelBase = source ? baseOf(source.kind, source.file) : null;
    modelLine.textContent = !source ? "" : modelBase ? `Model: ${shortName(source.file)} · ${modelBase}`
      : `Model: ${shortName(source.file)} · base unknown (look it up in its browser or Model info to check the LoRAs against it)`;
    for (const line of panel.querySelectorAll(".row[data-lora]")) {
      const loraBase = baseOf("loras", line.dataset.lora);
      const result = compareBases(loraBase, modelBase);
      line.classList.toggle("warn", result?.level === "warn");
      line.classList.toggle("bad", result?.level === "bad");
      const mark = line.querySelector(".mark");
      mark.textContent = result ? (result.level === "bad" ? "⛔" : "⚠️") : "";
      mark.title = result?.text ?? "";
    }
  }
  const timer = setInterval(checkBases, 3000);
  const onRemoved = node.onRemoved;
  node.onRemoved = function (...args) {
    clearInterval(timer);
    return onRemoved?.apply(this, args);
  };
  node.diceforgeStack = { render, checkBases };
  if (node.size[0] < 460) node.setSize([460, node.size[1]]); // Room for a row: name, info, group, 🎲, strengths. A loaded workflow's size wins (onConfigure).
  const onConfigure = node.onConfigure;
  node.onConfigure = function (...args) {
    const result = onConfigure?.apply(this, args);
    background(render()); // A loaded workflow's rows.
    return result;
  };
  background(render());
}

app.registerExtension({
  name: "DiceForge.LoraStack",
  nodeCreated(node) {
    if (node.comfyClass === NODE_TYPE) setUp(node);
  },
});

export { modelSource, fetchBases, baseOf }; // The connected model and its base, for the sampler presets' Auto (sampler_presets.js).
