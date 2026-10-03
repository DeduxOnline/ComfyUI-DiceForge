import { app } from "../../scripts/app.js";
import { addStyleOnce } from "./dom.js";
import { knownWildcards, PROMPT_FIELDS, PROMPT_NODE_TYPE, textareaOf, wildcardList } from "./wildcards.js";

// Syntax highlighting in the prompt fields of CLIP Dual Text Encode: __wildcards__ (red and wavy when no file has that name), {a|b} choices with
// their braces colored by depth, counts (2$$), weights (3::), locks (!), ${variables}, // and /* */ comments, \ escapes, (word:1.2) weights,
// embeddings and <lora:name:weight>. The text is drawn by a layer behind the field, which shows through it (the field keeps the caret, the selection and the editing).
// A setting turns it off.
const SETTING = "DiceForge.PromptHighlight";
const STYLE = `
.dfhl{position:absolute;overflow:hidden;pointer-events:none;white-space:pre-wrap;overflow-wrap:break-word;word-break:normal;box-sizing:border-box;margin:0;border:0;z-index:0}
textarea.dfhl-input{color:transparent!important;-webkit-text-fill-color:transparent!important;background:transparent!important;position:relative;z-index:1}
textarea.dfhl-input::placeholder{color:#888!important;-webkit-text-fill-color:#888!important}
textarea.dfhl-input::selection{background:rgba(90,140,230,.4);color:transparent}
.dfhl .wc{color:#7fd4ff}.dfhl .wc-missing{color:#ff8a8a;text-decoration:underline wavy #ff5c5c;text-decoration-skip-ink:none}
.dfhl .b0{color:#ffcf5c;font-weight:700}.dfhl .b1{color:#d79bff;font-weight:700}.dfhl .b2{color:#7fe0a8;font-weight:700}.dfhl .bad{color:#fff;background:#b33}
.dfhl .count{color:#ffa65c}.dfhl .weight{color:#ffa65c}.dfhl .lock{color:#ff6b9d;font-weight:700}.dfhl .var{color:#8be08b}
.dfhl .lora{color:#ff9ad5;font-weight:600}.dfhl .comment{color:#7a8a7a;font-style:italic}.dfhl .esc{color:#aaa}.dfhl .attn{color:#e0c07f}.dfhl .embed{color:#c4a3ff}
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
const COUNT = /^\s*(?:\d+(?:-\d*)?|-\d+)\$\$(?:[^{}]*?\$\$)?/; // {2$$, {1-3$$ and $$ (a choice's start only)
const OPTION = /^\s*(?:!\s*)?(?:\d+(?:\.\d+)?::)?(?:\s*!)?/; // 3::  !  !3::  3::! (an option's start)
const escapeHTML = (text) => text.replace(/[&<>"]/g, (char) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[char]);
function globTest(pattern) {
  const source = pattern.replace(/[.+^${}()|[\]\\]/g, "\\$&").replace(/\*/g, ".*").replace(/\?/g, ".");
  return new RegExp(`^${source}$`, "i");
}
// The marks for a prompt: [start, end, class] ranges. names: the known wildcard names, or null (not listed yet: nothing is called missing).
export function promptMarks(text, names) {
  const marks = [], stack = [], known = names && new Set(names.map((name) => name.toLowerCase()));
  const optionStart = (from) => { // A weight or lock right after { or |.
    const match = OPTION.exec(text.slice(from));
    if (!match?.[0].trim()) return;
    const lock = match[0].indexOf("!"), weight = match[0].search(/\d/);
    if (weight >= 0) marks.push([from + weight, from + match[0].indexOf("::") + 2, "weight"]);
    if (lock >= 0) marks.push([from + lock, from + lock + 1, "lock"]);
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
export function highlightPrompt(text, names) {
  let html = "", at = 0;
  for (const [start, end, kind] of promptMarks(text, names)) {
    if (start < at) continue; // Marks never overlap, but a weight inside another mark is skipped rather than drawn twice.
    html += escapeHTML(text.slice(at, start)) + `<span class="${kind}">${escapeHTML(text.slice(start, end))}</span>`;
    at = end;
  }
  return html + escapeHTML(text.slice(at)) + "\n"; // The last line break keeps its height, as in the field.
}
export function missingWildcards(text, names) {
  return promptMarks(text, names).filter(([, , kind]) => kind === "wc-missing").map(([start, end]) => text.slice(start, end));
}

// The layer behind a field: the field's content box and font, its background (the field itself turns transparent), its scroll position.
const layers = new Map(); // textarea -> { layer, background, color, title, key }
const COPIED = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "lineHeight", "letterSpacing", "wordSpacing", "tabSize", "textAlign", "textIndent",
  "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "borderTopLeftRadius", "borderTopRightRadius", "borderBottomLeftRadius", "borderBottomRightRadius"];
function attach(textarea) {
  const style = getComputedStyle(textarea);
  const layer = document.createElement("div");
  layer.className = "dfhl";
  textarea.parentElement.insertBefore(layer, textarea);
  const state = { layer, background: style.backgroundColor, color: style.color, title: textarea.getAttribute("title"), key: "" };
  layers.set(textarea, state);
  textarea.classList.add("dfhl-input");
  textarea.style.caretColor = state.color;
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
  const key = [textarea.value, textarea.offsetLeft, textarea.offsetTop, textarea.clientWidth, textarea.clientHeight, names?.length ?? -1].join("\u0001");
  if (key === state.key) return;
  state.key = key;
  const style = getComputedStyle(textarea), layer = state.layer;
  for (const property of COPIED) layer.style[property] = style[property];
  // Over the field's scrollbar too (its background, no gap), with that much more padding, so the text wraps at the same width as in the field.
  const scrollbar = Math.max(0, textarea.offsetWidth - textarea.clientWidth - 2 * textarea.clientLeft);
  Object.assign(layer.style, {
    left: `${textarea.offsetLeft + textarea.clientLeft}px`, top: `${textarea.offsetTop + textarea.clientTop}px`,
    width: `${textarea.clientWidth + scrollbar}px`, height: `${textarea.clientHeight}px`, paddingRight: `${parseFloat(style.paddingRight) + scrollbar}px`,
    background: state.background, color: state.color,
  });
  layer.innerHTML = highlightPrompt(textarea.value, names);
  layer.scrollTop = textarea.scrollTop;
  const missing = names ? missingWildcards(textarea.value, names) : [];
  if (missing.length) textarea.setAttribute("title", `No wildcard file for ${[...new Set(missing)].join(", ")}`);
  else if (state.title == null) textarea.removeAttribute("title");
  else textarea.setAttribute("title", state.title);
}
const enabled = () => app.extensionManager?.setting?.get?.(SETTING) !== false;
// Every half second: fields of new nodes get a layer, moved or resized ones follow, gone ones are let go; with the setting off, all are let go.
function scan() {
  const fields = new Set();
  if (enabled()) {
    for (const node of app.graph?.nodes ?? []) {
      if (node.comfyClass !== PROMPT_NODE_TYPE) continue;
      for (const name of PROMPT_FIELDS) {
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
    name: "Highlight the prompt syntax in CLIP Dual Text Encode",
    tooltip: "Colors __wildcards__ (red when no file has that name), {a|b} choices, weights, ${variables} and comments in the prompt fields.",
    type: "boolean",
    defaultValue: true,
  }],
  setup() {
    addStyleOnce("dfhl-style", STYLE);
    setInterval(scan, 500);
  },
});
