import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { background } from "./dom.js";
import { modelSource, fetchBases, baseOf } from "./lora_stack.js";
import { presetNameFor } from "./sampler_presets.js";
import { setField, PROMPT_NODE_TYPE } from "./wildcards.js";

// Prompt styles in the right-click menu of CLIP Dual Text Encode (prompt_styles.py): the quality tags each model family is made for, and your own
// styles (A1111's styles.csv). A style goes into both prompts: around the prompt where its text has {prompt}, after it otherwise. A style already in
// the prompts (✓ in the menu) is taken out again by a second click. Auto picks the family's style for the model connected to the node.
let styles = { builtin: [], user: [] };
async function request(path, options) {
  const response = await api.fetchApi(path, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}
async function loadStyles() {
  try { styles = await request("/diceforge/styles"); } catch { /* No answer: the menu offers what it had. */ }
  return styles;
}
function toast(severity, summary, detail) {
  const toaster = app.extensionManager?.toast;
  if (toaster?.add) toaster.add({ severity, summary, detail, life: 4000 });
  else if (severity === "error") alert(`${summary}: ${detail}`);
}

// The pieces of a style's text around {prompt} (or after the prompt), without the commas that join them.
const JOINING = /[\s,]/;
function trimJoin(text) {
  let start = 0, end = text.length;
  while (start < end && JOINING.test(text[start])) start++;
  while (end > start && JOINING.test(text[end - 1])) end--;
  return text.slice(start, end);
}
export function stylePieces(style) {
  if (!style?.trim()) return { before: "", after: "" };
  if (!style.includes("{prompt}")) return { before: "", after: trimJoin(style) };
  const [before, ...rest] = style.split("{prompt}");
  return { before: trimJoin(before), after: trimJoin(rest.join(" ")) };
}
const joined = (...parts) => parts.filter((part) => part.trim()).join(", ");
export function hasStyle(prompt, style) {
  const { before, after } = stylePieces(style);
  return (!before || prompt.includes(before)) && (!after || prompt.includes(after));
}
// The prompt with the style put in (pieces it already has are not added twice), or taken out.
export function withStyle(prompt, style) {
  const { before, after } = stylePieces(style);
  const text = trimJoin(prompt);
  return joined(before && !text.includes(before) ? before : "", text, after && !text.includes(after) ? after : "");
}
export function withoutStyle(prompt, style) {
  let text = prompt;
  for (const piece of Object.values(stylePieces(style))) if (piece) text = text.split(piece).join("");
  return trimJoin(text.replace(/[ \t]{2,}/g, " ").replace(/,(?:\s*,)+/g, ",").split(" ,").join(",")); // "a , , b" -> "a, b"
}
const fieldText = (node, name) => node.widgets?.find((widget) => widget.name === name)?.value ?? "";
const applied = (node, style) => (style.prompt.trim() || style.negative_prompt.trim()) && hasStyle(fieldText(node, "positive"), style.prompt) && hasStyle(fieldText(node, "negative"), style.negative_prompt);
function toggle(node, style) {
  const on = applied(node, style);
  for (const [field, text] of [["positive", style.prompt], ["negative", style.negative_prompt]]) {
    if (!text.trim()) continue;
    const now = fieldText(node, field);
    setField(node, field, on ? withoutStyle(now, text) : withStyle(now, text));
  }
  toast("success", "Prompt styles", `${on ? "Took out" : "Put in"} ${style.name}.${!on && style.note ? ` ${style.note}` : ""}`);
}

// Auto: the family's quality style for the model on the node's model input (or the one the sampler presets would pick by the file name).
const FAMILY_STYLES = { "Anima": "Anima quality", "Anima Turbo": "Anima quality", "Illustrious": "Illustrious quality", "NoobAI (eps)": "NoobAI quality",
  "NoobAI (v-pred)": "NoobAI v-pred quality" };
async function applyAuto(node) {
  const source = modelSource(node);
  if (!source) {
    toast("warn", "Prompt styles", "Auto needs the model connected to this node's model input (Load Checkpoint's MODEL).");
    return;
  }
  await fetchBases([source]);
  const base = baseOf(source.kind, source.file);
  const style = styles.builtin.find((item) => item.name === FAMILY_STYLES[presetNameFor(source.file, base)]);
  if (!style) {
    toast("warn", "Prompt styles", `No style for ${source.file.split(/[\\/]/).pop()}${base ? ` (${base})` : ""}: Anima, Illustrious and NoobAI are known.`);
    return;
  }
  if (!applied(node, style)) toggle(node, style);
  else toast("info", "Prompt styles", `${style.name} is already in the prompts.`);
}
async function saveCurrent(node) {
  const name = prompt("Name of the new style (the current positive and negative prompts):")?.trim();
  if (!name) return;
  if (styles.user.some((item) => item.name.toLowerCase() === name.toLowerCase()) && !confirm(`A style named "${name}" already exists. Replace it?`)) return;
  try {
    await request("/diceforge/styles", { method: "POST", body: JSON.stringify({ name, prompt: fieldText(node, "positive"), negative_prompt: fieldText(node, "negative") }) });
    toast("success", "Prompt styles", `Saved ${name}.`);
  } catch (error) {
    toast("error", "Prompt styles", error.message);
  }
  await loadStyles();
}
async function deleteStyle(name) {
  if (!confirm(`Delete the style "${name}"?`)) return;
  try {
    await request(`/diceforge/styles?${new URLSearchParams({ name })}`, { method: "DELETE" });
    toast("success", "Prompt styles", `Deleted ${name}.`);
  } catch (error) {
    toast("error", "Prompt styles", error.message);
  }
  await loadStyles();
}

const run = (promise) => background(promise.catch((error) => toast("error", "Prompt styles", error.message)));
// The entries of the submenu (also what the tests click).
export function styleItems(node) {
  const styleItem = (style, mark) => ({ content: `${applied(node, style) ? "✓" : mark} ${style.name}`, callback: () => toggle(node, style) });
  return [
    { content: "✨ Auto (quality tags for the connected model)", callback: () => run(applyAuto(node)) },
    null,
    ...styles.builtin.map((style) => styleItem(style, "🎨")),
    ...(styles.user.length ? [null, ...styles.user.map((style) => styleItem(style, "★"))] : []),
    null,
    { content: "💾 Save the prompts as a style…", callback: () => run(saveCurrent(node)) },
    ...styles.user.map((style) => ({ content: `🗑 Delete ${style.name}`, callback: () => run(deleteStyle(style.name)) })),
  ];
}

app.registerExtension({
  name: "DiceForge.PromptStyles",
  setup() {
    background(loadStyles());
  },
  getNodeMenuItems(node) {
    if (node.comfyClass !== PROMPT_NODE_TYPE) return [];
    return [{ content: "🎨 Prompt styles", has_submenu: true, submenu: { options: styleItems(node) } }];
  },
});
