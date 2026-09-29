import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openModelInfo } from "./model_info.js";
import { openModelBrowser, BROWSERS } from "./model_browser.js";

// LoRA Stack (lora_stack.py): the rows of LoRAs drawn in the node, like rgthree's Power Lora Loader. The node's "loras" text input holds them as JSON;
// it is hidden and this panel edits it. Each row: on/off, the LoRA (click to change it in the LoRA Browser), Model info, a group, a fixed strength or
// a random range (🎲), and the CLIP strength when it is set apart. Groups (A-D) take turns: "use 1 to 2 of these".
const NODE_TYPE = "DiceForgeLoraStack";
const GROUPS = ["A", "B", "C", "D"];
const LORAS = BROWSERS.find((spec) => spec.kind === "loras");
const EMPTY = { rows: [], groups: {}, separate_clip: false };

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
`;
function addStyle() {
  if (document.getElementById("dfls-style")) return;
  const style = document.createElement("style");
  style.id = "dfls-style";
  style.textContent = STYLE;
  document.head.append(style);
}
function element(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child instanceof Node ? child : document.createTextNode(String(child ?? "")));
  return node;
}
const shortName = (file) => file.split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
const round = (value) => Math.round(value * 100) / 100;

let loraFiles = null; // The files of the loras folders, to mark rows whose file is missing.
async function loraList() {
  if (!loraFiles) {
    try { loraFiles = new Set(await (await api.fetchApi("/models/loras")).json()); } catch { loraFiles = new Set(); }
  }
  return loraFiles;
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
  const widget = node.addDOMWidget("lora_stack", "diceforge_lora_stack", panel, { serialize: false, getMinHeight: () => panel.scrollHeight + 6 });
  widget.serialize = false;
  const read = () => {
    try { return { ...EMPTY, ...JSON.parse(data.value || "{}") }; } catch { return structuredClone(EMPTY); }
  };
  const write = (stack) => {
    data.value = JSON.stringify(stack);
    data.callback?.(data.value);
    render();
    node.setDirtyCanvas?.(true, true);
  };
  const update = (change) => { const stack = read(); change(stack); write(stack); };
  const browse = (target) => openModelBrowser(node, LORAS, target);
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
      const line = element("div", { class: "row" + (row.on === false ? " off" : "") + (missing ? " missing" : ""), title: missing ? `${row.lora} is not in the loras folders` : "" },
        element("span", { class: "grip", title: "Drag to reorder" }, "⋮⋮"),
        toggle,
        element("span", { class: "name", title: `${row.lora}\nClick to pick another LoRA`, onclick: () => browse({
          label: "Choose", hint: `Choose puts a LoRA in this row (instead of ${shortName(row.lora)}).`,
          pick: (file) => { set((r) => { r.lora = file; }); return true; },
        }) }, shortName(row.lora)),
        element("button", { title: "Model info", onclick: () => openModelInfo("loras", row.lora) }, "ℹ"),
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
        label: "+ Add", hint: "+ Add adds a LoRA to the stack; add as many as you like, then close.",
        pick: (file) => { update((next) => { next.rows.push({ on: true, lora: file, strength: 1, clip: 1, random: false, group: "" }); }); return `${shortName(file)} added to the stack.`; },
      }) }, "＋ Add LoRA"),
      element("label", { class: "foot muted" }, separate, "Separate CLIP strength"));
    if (!node.flags?.collapsed && node.size[1] < node.computeSize()[1]) node.setSize([node.size[0], node.computeSize()[1]]);
  }
  node.diceforgeStack = { render };
  if (node.size[0] < 460) node.setSize([460, node.size[1]]); // Room for a row: name, info, group, 🎲, strengths. A loaded workflow's size wins (onConfigure).
  const onConfigure = node.onConfigure;
  node.onConfigure = function (...args) {
    const result = onConfigure?.apply(this, args);
    render(); // A loaded workflow's rows.
    return result;
  };
  render();
}

app.registerExtension({
  name: "DiceForge.LoraStack",
  nodeCreated(node) {
    if (node.comfyClass === NODE_TYPE) setUp(node);
  },
});
