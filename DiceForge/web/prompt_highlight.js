import { app } from "../../scripts/app.js";
import { addStyleOnce } from "./dom.js";
import { fieldsOf, knownWildcards, textareaOf, wildcardList } from "./wildcards.js";

// Syntax highlighting in the prompt fields of CLIP Dual Text Encode: __wildcards__ (red and wavy when no file has that name), {a|b} choices with
// their braces colored by depth, counts (2$$), weights (3::), locks (!), ${variables}, // and /* */ comments, \ escapes, (word:1.2) weights,
// embeddings and <lora:name:weight>. The text is drawn by a layer behind the field, which shows through it (the field keeps the caret, the selection and the editing).
// The Wildcard Browser's editor uses it too, with the wildcard files' # comment lines and 3:: line weights. A setting turns it off.
const SETTING = "DiceForge.PromptHighlight";
const STYLE = `
.dfhl{position:absolute;overflow:hidden;pointer-events:none;white-space:pre-wrap;overflow-wrap:break-word;word-break:normal;box-sizing:border-box;margin:0;border:0;z-index:0}
textarea.dfhl-input{color:transparent!important;-webkit-text-fill-color:transparent!important;background:transparent!important;position:relative;z-index:1}
textarea.dfhl-input::placeholder{color:var(--descrip-text,#888)!important;-webkit-text-fill-color:var(--descrip-text,#888)!important}
textarea.dfhl-input::selection{background:rgba(90,140,230,.4);color:transparent}
.dfhl{--dfhl-fg:#ddd}.dfhl .wc{color:color-mix(in srgb,#2196f3 55%,var(--dfhl-fg))}
.dfhl .wc-missing{color:color-mix(in srgb,#e53935 60%,var(--dfhl-fg));text-decoration:underline wavy #e53935;text-decoration-skip-ink:none}
.dfhl .b0{color:color-mix(in srgb,#f9a825 55%,var(--dfhl-fg));font-weight:700}.dfhl .b1{color:color-mix(in srgb,#ab47bc 55%,var(--dfhl-fg));font-weight:700}
.dfhl .b2{color:color-mix(in srgb,#43a047 55%,var(--dfhl-fg));font-weight:700}.dfhl .bad{color:#fff;background:#b33}
.dfhl .count,.dfhl .weight{color:color-mix(in srgb,#fb8c00 55%,var(--dfhl-fg))}.dfhl .lock{color:color-mix(in srgb,#e91e63 55%,var(--dfhl-fg));font-weight:700}
.dfhl .var{color:color-mix(in srgb,#7cb342 55%,var(--dfhl-fg))}.dfhl .lora{color:color-mix(in srgb,#ec407a 50%,var(--dfhl-fg));font-weight:600}
.dfhl .comment{color:color-mix(in srgb,#78909c 50%,var(--dfhl-fg));font-style:italic}.dfhl .esc{color:color-mix(in srgb,var(--dfhl-fg) 65%,transparent)}
.dfhl .attn{color:color-mix(in srgb,#c49a2c 55%,var(--dfhl-fg))}.dfhl .embed{color:color-mix(in srgb,#7e57c2 55%,var(--dfhl-fg))}
`;

const NAME_CHAR = String.raw`[\p{L}\p{M}\p{N}_\-./*?]|\$\{\w+\}`; // As the node reads names (clip_text_encode_pos_neg.WILDCARD_PATTERN).
const TOKENS = new RegExp([
  String.raw`(?<esc>\\[{}|!\\])`,
  String.raw`(?<lora><\s*(?:lora|lyco)\s*:[^<>\n]*>)`,
  String.raw`(?<wc>__(?:${NAME_CHAR})+?(?: (?:${NAME_CHAR})+?)*?__)`,
  String.raw`(?<comment>\/\*[\s\S]*?\*\/|\/\/[^\n]*)`,
  String.raw`(?<varset>\$\{\s*[A-Za-z_]\w*\s*=!?)`,
  String.raw`(?<varuse>\$\{\s*[A-Za-z_]\w*\s*\})`,
  String.raw`(?<attn>:\s*-?\d+(?:\.\d+)?(?=\s*\)))`,
  String.raw`(?<embed>\bembedding:[^\s,()]+)`,
  String.raw`(?<open>\{)`, String.raw`(?<close>\})`, String.raw`(?<bar>\|)`,
].join("|"), "gu");
const COUNT = /^\s*(?:\d+(?:-\d*)?|-\d+)\$\$(?:[^{}$]*\$\$)?/; // {2$$, {1-3$$ and $$ (a choice's start only)
const WEIGHT_START = /^\d+(?:\.\d+)?::/; // 3:: or 1.5:: (an option's weight)
const escapeHTML = (text) => text.replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[char]);
function globTest(pattern) {
  const source = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`^${source}$`, "i");
}
// The marks for a prompt: [start, end, class] ranges. names: the known wildcard names, or null (not listed yet: nothing is called missing).
export function promptMarks(text, names) {
  const marks = [], stack = [], known = names && new Set(names.map((name) => name.toLowerCase()));
  const spacesFrom = (at) => { while (at < text.length && /\s/.test(text[at])) at++; return at; };
  const optionStart = (from) => { // A weight or lock right after { or |: 3::  !  !3::  3::!  (spaces allowed between)
    let at = spacesFrom(from), lock = -1;
    if (text[at] === "!") lock = at, at = spacesFrom(at + 1);
    const weight = WEIGHT_START.exec(text.slice(at, at + 40));
    if (weight) {
      marks.push([at, at + weight[0].length, "weight"]);
      const after = spacesFrom(at + weight[0].length);
      if (lock < 0 && text[after] === "!") lock = after;
    }
    if (lock >= 0) marks.push([lock, lock + 1, "lock"]);
  };
  for (const match of text.matchAll(TOKENS)) {
    const start = match.index, end = start + match[0].length, group = Object.entries(match.groups).find(([, value]) => value !== undefined)[0];
    if (group === "open") {
      stack.push({ start, kind: "choice", mark: marks.length });
      marks.push([start, end, `b${(stack.length - 1) % 3}`]);
      const count = COUNT.exec(text.slice(end));
      if (count) marks.push([end, end + count[0].length, "count"]);
      optionStart(end + (count ? count[0].length : 0));
    } else if (group === "varset") {
      stack.push({ start, kind: "var", mark: marks.length });
      marks.push([start, end, "var"]);
    } else if (group === "close") {
      const open = stack.pop();
      marks.push([start, end, !open ? "bad" : open.kind === "var" ? "var" : `b${stack.length % 3}`]);
    } else if (group === "bar") {
      const top = stack.at(-1);
      if (top?.kind === "choice") {
        marks.push([start, end, `b${(stack.length - 1) % 3}`]);
        optionStart(end);
      }
    } else if (group === "wc") {
      const name = match[0].slice(2, -2);
      const missing = known && !name.includes("${") && (/[*?]/.test(name) ? !names.some((item) => globTest(name).test(item)) : !known.has(name.toLowerCase()));
      marks.push([start, end, missing ? "wc-missing" : "wc"]);
    } else if (group === "varuse") marks.push([start, end, "var"]);
    else marks.push([start, end, group]); // esc, lora, comment, attn, embed
  }
  for (const open of stack) marks[open.mark][2] = "bad"; // Never closed.
  return marks.sort((a, b) => a[0] - b[0]);
}
// The marks for a wildcard file: every line is one option, read as a prompt of its own, after a # comment line or a 3:: line weight.
const LINE_WEIGHT = /^\s*\d+(?:\.\d+)?::/;
export function wildcardFileMarks(text, names) {
  const marks = [];
  let offset = 0;
  for (const line of text.split("\n")) {
    if (/^\s*#/.test(line)) marks.push([offset, offset + line.length, "comment"]);
    else {
      const weight = LINE_WEIGHT.exec(line), from = weight ? weight[0].length : 0;
      if (weight) marks.push([offset + weight[0].search(/\d/), offset + from, "weight"]);
      for (const [start, end, kind] of promptMarks(line.slice(from), names)) marks.push([offset + from + start, offset + from + end, kind]);
    }
    offset += line.length + 1;
  }
  return marks;
}
function marksHTML(text, marks) {
  let html = "", at = 0;
  for (const [start, end, kind] of marks) {
    if (start < at) continue; // Marks never overlap, but a weight inside another mark is skipped rather than drawn twice.
    html += escapeHTML(text.slice(at, start)) + `<span class="${kind}">${escapeHTML(text.slice(start, end))}</span>`;
    at = end;
  }
  return html + escapeHTML(text.slice(at)) + "\n"; // The last line break keeps its height, as in the field.
}
export const highlightPrompt = (text, names) => marksHTML(text, promptMarks(text, names));
export const highlightWildcardFile = (text, names) => marksHTML(text, wildcardFileMarks(text, names));
export const highlightEnabled = () => app.extensionManager?.setting?.get?.(SETTING) !== false;
export const addHighlightStyle = () => addStyleOnce("dfhl-style", STYLE);
export function missingWildcards(text, names) {
  return promptMarks(text, names).filter(([, , kind]) => kind === "wc-missing").map(([start, end]) => text.slice(start, end));
}

// The layer behind a field: the field's content box and font, its background (the field itself turns transparent), its scroll position.
const layers = new Map(); // textarea -> { layer, background, color, title, key }
// The palette's field colors: when they change, the layer reads the field's colors again.
const palette = () => {
  const root = getComputedStyle(document.documentElement);
  return ["--comfy-input-bg", "--input-text", "--component-node-widget-background", "--component-node-foreground"].map((name) => root.getPropertyValue(name)).join(" ");
};
// The field's own colors, read with the class that makes it transparent taken off for that moment (nothing is drawn in between).
function fieldColors(textarea, state) {
  textarea.classList.remove("dfhl-input");
  const style = getComputedStyle(textarea);
  state.background = style.backgroundColor;
  state.color = style.color;
  textarea.classList.add("dfhl-input");
  textarea.style.caretColor = state.color;
  state.layer.style.setProperty("--dfhl-fg", state.color);
}
const COPIED = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing", "wordSpacing", "tabSize", "textAlign", "textIndent",
  "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "borderTopLeftRadius", "borderTopRightRadius", "borderBottomLeftRadius", "borderBottomRightRadius"];
function attach(textarea) {
  const style = getComputedStyle(textarea);
  const layer = document.createElement("div");
  layer.className = "dfhl";
  textarea.parentElement.insertBefore(layer, textarea);
  const state = { layer, background: style.backgroundColor, color: style.color, title: textarea.getAttribute("title"), key: "", palette: palette() };
  layers.set(textarea, state);
  textarea.classList.add("dfhl-input");
  textarea.style.caretColor = state.color;
  layer.style.setProperty("--dfhl-fg", state.color);
  textarea.addEventListener("scroll", () => { layer.scrollTop = textarea.scrollTop; layer.scrollLeft = textarea.scrollLeft; });
  textarea.addEventListener("input", () => sync(textarea));
  sync(textarea);
}
function detach(textarea) {
  const state = layers.get(textarea);
  if (!state) return;
  state.layer.remove();
  textarea.classList.remove("dfhl-input");
  textarea.style.caretColor = "";
  if (state.title == null) textarea.removeAttribute("title"); else textarea.setAttribute("title", state.title);
  layers.delete(textarea);
}
function sync(textarea) {
  const state = layers.get(textarea);
  if (!state) return;
  const names = knownWildcards();
  const colors = palette();
  const key = [textarea.value, textarea.offsetLeft, textarea.offsetTop, textarea.clientWidth, textarea.clientHeight, names?.length ?? -1, colors].join("\u0001");
  if (key === state.key) return;
  state.key = key;
  if (colors !== state.palette) {
    state.palette = colors;
    fieldColors(textarea, state);
  }
  const style = getComputedStyle(textarea), layer = state.layer;
  for (const property of COPIED) layer.style[property] = style[property];
  // Over the field's scrollbar too (its background, no gap), with that much more padding, so the text wraps at the same width as in the field.
  const scrollbar = Math.max(0, textarea.offsetWidth - textarea.clientWidth - 2 * textarea.clientLeft);
  Object.assign(layer.style, {
    left: `${textarea.offsetLeft + textarea.clientLeft}px`, top: `${textarea.offsetTop + textarea.clientTop}px`,
    width: `${textarea.clientWidth + scrollbar}px`, height: `${textarea.clientHeight}px`, paddingRight: `${Number.parseFloat(style.paddingRight) + scrollbar}px`,
    background: state.background, color: state.color,
  });
  layer.innerHTML = highlightPrompt(textarea.value, names);
  layer.scrollTop = textarea.scrollTop;
  const missing = names ? missingWildcards(textarea.value, names) : [];
  if (missing.length) textarea.setAttribute("title", `No wildcard file for ${[...new Set(missing)].join(", ")}`);
  else if (state.title == null) textarea.removeAttribute("title");
  else textarea.setAttribute("title", state.title);
}
// Every half second: fields of new nodes get a layer, moved or resized ones follow, gone ones are let go; with the setting off, all are let go.
function scan() {
  const fields = new Set();
  if (highlightEnabled()) {
    for (const node of app.graph?.nodes ?? []) {
      for (const name of fieldsOf(node) ?? []) {
        const textarea = textareaOf(node, name);
        if (textarea?.isConnected && textarea.parentElement) fields.add(textarea);
      }
    }
  }
  for (const textarea of [...layers.keys()]) {
    if (!fields.has(textarea) || !textarea.isConnected || layers.get(textarea).layer.parentElement !== textarea.parentElement) detach(textarea);
  }
  for (const textarea of fields) {
    if (!layers.has(textarea)) attach(textarea);
    else sync(textarea);
  }
  if (fields.size && !knownWildcards()) wildcardList().catch(() => {}); // The names, for the missing ones.
}

app.registerExtension({
  name: "DiceForge.PromptHighlight",
  settings: [{
    id: SETTING,
    category: ["DiceForge", "Prompts", "Highlight"],
    name: "Highlight the prompt syntax in CLIP Dual Text Encode and the Wildcard Browser",
    tooltip: "Colors __wildcards__ (red when no file has that name), {a|b} choices, weights, ${variables} and comments in the prompt fields and the wildcard editor.",
    type: "boolean",
    defaultValue: true,
  }],
  setup() {
    addHighlightStyle();
    setInterval(scan, 500);
  },
});
