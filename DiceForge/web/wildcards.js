import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, background, element } from "./dom.js";
import { dragSource, dropTarget, pickFolder } from "./move_dialog.js";
import { addHighlightStyle, highlightEnabled, highlightWildcardFile } from "./prompt_highlight.js";
import { keepSize, recall, remember, scrollBack } from "./window_memory.js";
import { closeMenu, menuAt, menuButton, menuOpen, moveCursor, slashToSearch, typingIn, withMenu } from "./menu.js";

// Wildcards in CLIP Dual Text Encode: autocomplete after "__" in the prompt fields, and the Wildcard Browser (node menu) with a folder tree,
// "+ Add" buttons that insert __name__ (or __folder/*__) where the cursor was, and an editor for the files.
const NODE_TYPE = "CLIPTextEncodePositiveNegative";
const FIELDS = ["positive", "negative"];
// The nodes whose text fields get the prompt tools (autocomplete, highlighting, the browsers' + Add, the syntax guide), and their fields.
const PROMPT_NODES = { [NODE_TYPE]: FIELDS, DiceForgeWildcardsToText: ["text"] };
const fieldsOf = (node) => PROMPT_NODES[node?.comfyClass] ?? null;
const isPromptNode = (node) => !!fieldsOf(node);

// The wildcard list, fetched once and shared: keystrokes while it loads wait for the same request instead of each sending one (their answers could
// come back in any order). listCache is the last list that arrived, for drawing the browser.
let listCache = null, listRequest = null;
function wildcardList(refresh = false) {
  if (!listRequest || refresh) {
    const request = api.fetchApi("/diceforge/wildcards")
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`${response.status}`))))
      .then((list) => { if (listRequest === request) listCache = list; return list; }, // An older request finishing late doesn't win.
        () => { if (listRequest === request) listRequest = null; return listCache ?? { files: [], folders: [] }; }); // Failed: the next use asks again.
    listRequest = request;
  }
  return listRequest;
}
// Folders of the wildcard names ("hair/long/x" is in "hair" and "hair/long").
function folderNames(files) {
  const folders = new Set();
  for (const { name } of files) {
    const parts = name.split("/").slice(0, -1);
    parts.forEach((_, index) => folders.add(parts.slice(0, index + 1).join("/")));
  }
  return [...folders].sort((a, b) => a.localeCompare(b));
}

// The node and prompt field (positive or negative) a textarea belongs to, in the Nodes 2.0 and the classic canvas. Nodes 2.0 shows the field's
// label next to its textarea; the positive and negative textareas are also the node's only ones, in that order.
function textareasOf(nodeId) {
  return [...document.querySelectorAll(`[data-node-id="${nodeId}"] textarea`)];
}
function fieldOf(textarea) {
  const nodeElement = textarea.closest?.("[data-node-id]");
  if (nodeElement) {
    const node = app.graph?.getNodeById(Number(nodeElement.dataset.nodeId)) ?? app.graph?.getNodeById(nodeElement.dataset.nodeId);
    const fields = fieldsOf(node);
    if (!fields) return null;
    const labelText = textarea.closest('[data-testid="node-widget"]')?.innerText?.trim();
    const byLabel = node.widgets?.find((widget) => fields.includes(widget.name) && labelText && labelText.startsWith(widget.label || widget.name))?.name;
    const name = byLabel ?? fields[textareasOf(nodeElement.dataset.nodeId).indexOf(textarea)];
    return name ? { node, name } : null;
  }
  for (const node of app.graph?.nodes ?? []) {
    const fields = fieldsOf(node);
    if (!fields) continue;
    const widget = node.widgets?.find((widget) => fields.includes(widget.name) && (widget.inputEl === textarea || widget.element?.contains?.(textarea)));
    if (widget) return { node, name: widget.name };
  }
  return null;
}
function textareaOf(node, name) {
  const inNodes2 = textareasOf(node.id).find((textarea) => fieldOf(textarea)?.name === name);
  return inNodes2 ?? node.widgets?.find((widget) => widget.name === name)?.inputEl ?? null;
}
// Where the cursor was last, per node: the field and the selection, so "+ Add" in the browser inserts there.
const lastCursor = new WeakMap();
function rememberCursor(event) {
  const textarea = event.target;
  if (textarea?.tagName !== "TEXTAREA") return;
  const field = fieldOf(textarea);
  if (field) lastCursor.set(field.node, { name: field.name, start: textarea.selectionStart, end: textarea.selectionEnd });
}
// Sets a prompt field's text through its widget (what the workflow saves and runs) and its textarea (what is shown).
function setField(node, name, text, caret) {
  const widget = node.widgets?.find((widget) => widget.name === name);
  if (widget) {
    widget.value = text;
    widget.callback?.(text);
  }
  const textarea = textareaOf(node, name);
  if (textarea) {
    textarea.value = text;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    if (caret != null) {
      textarea.focus();
      textarea.setSelectionRange(caret, caret);
    }
  }
  node.setDirtyCanvas?.(true, true);
}
// The field insertIntoNode would put text in: the one asked for, else the one the cursor was last in, else the first.
function cursorField(node, field) {
  return field ?? lastCursor.get(node)?.name ?? fieldsOf(node)?.[0] ?? "positive";
}
// Inserts at the cursor last in the node's prompt fields (or at the end of the positive prompt), or at the end of the field asked for (field) when
// the cursor wasn't in it.
function insertIntoNode(node, token, field) {
  const last = lastCursor.get(node);
  const cursor = (field && last?.name !== field ? { name: field } : last) ?? { name: fieldsOf(node)?.[0] ?? "positive" };
  const current = String(node.widgets?.find((widget) => widget.name === cursor.name)?.value ?? "");
  let start = cursor.start ?? current.length, end = cursor.end ?? current.length;
  // Commas around the token when it would touch other text (no cursor yet: added at the end, after a comma).
  const before = current.slice(0, start), after = current.slice(end);
  const insert = (before && !/[\s,{|(]$/.test(before) ? ", " : "") + token + (after && !/^[\s,}|)]/.test(after) ? ", " : "");
  const text = current.slice(0, start) + insert + current.slice(end);
  setField(node, cursor.name, text, start + insert.length);
  lastCursor.set(node, { name: cursor.name, start: start + insert.length, end: start + insert.length });
  return cursor.name;
}

const STYLE = `
.dfwc-pop{position:fixed;z-index:10001;background:#262626;border:1px solid #555;border-radius:6px;box-shadow:0 6px 20px #000a;font:13px system-ui,sans-serif;color:#ddd;min-width:220px;max-width:420px;max-height:280px;overflow:auto;padding:3px}
.dfwc-pop div{padding:4px 8px;border-radius:4px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dfwc-pop div.on{background:#3a5a8a;color:#fff}
.dfwc .picks{border:1px solid #4a6a9a;background:#2a3444;border-radius:6px;padding:6px 8px;margin-top:8px;max-height:32%;overflow:auto}
.dfwc .picks-head{display:flex;gap:8px;align-items:center;margin-bottom:4px}.dfwc .picks .pick{display:flex;gap:8px;align-items:center;padding:3px 0;border-top:1px solid #3a4a64}
.dfwc .picks .pick .text{flex:1;min-width:0;white-space:pre-wrap;word-break:break-word}.dfwc .picks button{padding:1px 8px;font-size:12px}
.dfwc .row .broken{color:#ff8a8a;cursor:help}.dfwc .row.cursor{outline:1px solid #6a9ad8;outline-offset:-1px}.dfwc .top{flex-wrap:wrap}
.dfwc .replace{border:1px solid #6a5a9a;background:#2e2a44;border-radius:6px;padding:6px 8px;margin-top:8px;max-height:36%;overflow:auto}
.dfwc .replace-head{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.dfwc .replace-head input{flex:1;min-width:140px}
.dfwc .replace .change{display:flex;gap:8px;padding:3px 0;border-top:1px solid #443c64;font-size:12px}.dfwc .replace .change b{min-width:120px}
.dfwc .replace .change .after{color:#9c9}.dfwc .replace .change .before{color:#c99;text-decoration:line-through}.dfwc .status button.more-action{margin-left:6px;padding:0 8px;font-size:12px}
.dfwc .row button.more{border:none;background:none;color:#999;padding:0 4px;font-size:15px}.dfwc .row button.more:hover{color:#fff}.dfwc-pop .n{color:#999;float:right;margin-left:12px}.dfwc-pop .browse{color:#9cc8ff;border-top:1px solid #444;margin-top:2px}
.dfwc-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dfwc{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(1100px,95vw);height:min(760px,90vh);display:flex;flex-direction:column;padding:16px 18px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dfwc h2{margin:0 0 10px;font-size:20px;color:#fff}.dfwc .top{display:flex;gap:8px;margin-bottom:10px}
.dfwc input,.dfwc textarea{background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:6px 8px;font:inherit;box-sizing:border-box}
.dfwc .top input{flex:1}.dfwc .main{display:flex;gap:12px;flex:1;min-height:0}
.dfwc .tree{width:calc((100% - 12px) / 3);flex:none;box-sizing:border-box;overflow:auto;border:1px solid #4a4a4a;border-radius:6px;padding:6px}
.dfwc .edit{flex:1;display:flex;flex-direction:column;gap:8px;min-width:0}
.dfwc .code{--current-line:-40px;position:relative;flex:1;display:flex;min-height:0;border:1px solid #555;border-radius:4px;background:#262626;overflow:hidden}
.dfwc .code .lines,.dfwc .code .hl,.dfwc .code textarea{font:13px/20px ui-monospace,monospace;letter-spacing:normal}
.dfwc .code .lines,.dfwc .code .hl{background-image:linear-gradient(#2e3846,#2e3846),linear-gradient(to bottom,transparent 19px,#323232 19px);
  background-size:100% 20px;background-position:0 var(--current-line),0 6px;background-repeat:no-repeat,repeat;background-attachment:local}
.dfwc .code .lines{flex:none;box-sizing:content-box;padding:6px 8px 40px 24px;text-align:right;color:#6f6f6f;white-space:pre;overflow:hidden;user-select:none;background-color:#212121;border-right:1px solid #444}
.dfwc .code .text{flex:1;min-width:0;position:relative;display:flex}
.dfwc .code .hl{position:absolute;inset:0;margin:0;padding:6px 48px 46px 8px;white-space:pre;overflow:hidden;color:#eee;background-color:#262626;pointer-events:none;z-index:0}
.dfwc .code .hl span{font-weight:inherit}
.dfwc .code textarea.src{flex:1;min-width:0;resize:none;border:none;border-radius:0;padding:6px 8px;white-space:pre;overflow:auto;position:relative;z-index:1;outline:none;
  background:transparent;color:transparent;-webkit-text-fill-color:transparent;caret-color:#eee}
.dfwc .code textarea.src::placeholder{color:#888;-webkit-text-fill-color:#888}.dfwc .code textarea.src::selection{background:rgba(90,140,230,.4)}
.dfwc .code.readonly .hl{color:#aaa}
.dfwc .code button.line-add{position:absolute;left:3px;z-index:2;width:18px;height:18px;padding:0;border-radius:4px;font:13px/16px system-ui,sans-serif;border-color:#4a7a4a;color:#bfe8bf;background:#253325}
.dfwc .row .found{color:#9cc8ff;font-style:italic;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:45%}.dfwc.drop-zip{outline:3px dashed #8fd0a8}
.dfwc [hidden]{display:none!important}.dfwc .cards{flex:1;display:flex;flex-direction:column;gap:8px;min-width:0;min-height:0}
.dfwc .cards-head{display:flex;gap:8px;align-items:center;color:#ccc}.dfwc .cards-head b{color:#fff}.dfwc .cards-head .muted{flex:1}
.dfwc .cards .grid{flex:1;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(150px,1fr));gap:10px;align-content:start;grid-auto-rows:max-content;padding-right:4px}
.dfwc .card{border:1px solid #4a4a4a;border-radius:8px;overflow:hidden;background:#2e2e2e;display:flex;flex-direction:column}
.dfwc .card .pic{flex:none;aspect-ratio:3/4;background:#1e1e1e;display:flex;align-items:center;justify-content:center;overflow:hidden}
.dfwc .card .pic img{width:100%;height:100%;object-fit:cover;display:block}.dfwc .card .pic .none{color:#888;font-size:12px;padding:10px;text-align:center;word-break:break-word}
.dfwc .card .info{padding:6px 8px;display:flex;flex-direction:column;gap:4px;flex:1}.dfwc .card .title{font-weight:600;color:#fff;word-break:break-word;cursor:pointer}
.dfwc .card .line{color:#aaa;font-size:12px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;word-break:break-word}
.dfwc .card .actions{display:flex;gap:6px;justify-content:space-between;align-items:center;margin-top:auto}
.dfwc button.mode.on{border-color:#6a9ad8;background:#2f3f55}
.dfwc .row{display:flex;align-items:center;gap:6px;padding:3px 6px;border-radius:4px}.dfwc .row:hover{background:#2c2c2c}
.dfwc .row .name{flex:1;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dfwc .row.sel{background:#2f3f55}
.dfwc .folder>.row .name{font-weight:600}.dfwc .folder>.row .name::before{content:"▸ ";color:#999}.dfwc .folder.open>.row .name::before{content:"▾ "}
.dfwc .kids{margin-left:16px}.dfwc button.fav{border:none;background:none;padding:0 4px;font-size:15px;color:#888}.dfwc button.fav.on{color:#ffd24a}
.dfwc button.only-favorites.on{border-color:#b8962e;color:#ffd24a}.dfwc .row.drop,.dfwc .tree.drop{background:#35584a;outline:1px dashed #8fd0a8}.dfwc .folder:not(.open)>.kids{display:none}.dfwc .muted{color:#999;font-size:12px}
.dfwc button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit}.dfwc button:hover{background:#2c2c2c}
.dfwc button.convert{padding:1px 7px;font-size:12px;border-color:#5a6f9a;color:#bcd0f5}.dfwc .row button.export{padding:1px 7px;font-size:12px}.dfwc .edit button.convert{padding:5px 12px;font-size:inherit}
.dfwc .card .actions button.picture,.dfwc .card .actions button.no-picture{padding:1px 6px;font-size:12px}.dfwc .card.drop{outline:2px dashed #8fd0a8}
.dfwc button:disabled{opacity:.5;cursor:default}.dfwc button.delete:not(:disabled){border-color:#8a4a4a;color:#f0b0b0}.dfwc textarea[readonly]{color:#aaa}.dfwc button.add{padding:1px 8px;font-size:12px;border-color:#4a7a4a;color:#bfe8bf}.dfwc .status{color:#9c9;min-height:18px;font-size:13px}.dfwc .status button.undo{margin-left:10px;padding:0 8px;font-size:12px}
`;
const addStyle = () => addStyleOnce("dfwc-style", STYLE);

// Autocomplete in the prompt fields, from sources tried in order: the wildcards and folders (folder/*) after an opening "__" (an odd number of "__"
// before the cursor), the LoRA files after "<lora:", and what other extensions add (prompt tags, tag_autocomplete.js). A source looks at the text
// before the cursor and gives null (not its turn) or { start, items, skip }: items (or a promise of them) are { label, hint, insert, favorite,
// browse }, and accepting one replaces the text from start to the cursor (and a typed skip right after it) with its insert.
const popup = { element: null, textarea: null, items: [], index: 0, start: 0, skip: null };
const sources = [];
export function addCompletionSource(source, first = false) {
  if (first) sources.unshift(source);
  else sources.push(source);
}
// Where the caret is on the screen: a hidden copy of the field, laid out like it (each side's padding and border: the shorthands read empty in
// some browsers, and a copy without them wraps the lines elsewhere), measured to the caret, then scaled like the field is (Nodes 2.0 zooms the
// nodes with a CSS transform, so the field's own sizes differ from its size on the screen).
const MIRRORED = ["fontFamily", "fontSize", "fontWeight", "fontStyle", "fontVariant", "lineHeight", "letterSpacing", "wordSpacing", "textTransform", "textIndent",
  "tabSize", "boxSizing", "paddingTop", "paddingRight", "paddingBottom", "paddingLeft", "borderTopWidth", "borderRightWidth", "borderBottomWidth", "borderLeftWidth",
  "borderTopStyle", "borderRightStyle", "borderBottomStyle", "borderLeftStyle", "whiteSpace", "wordBreak", "overflowWrap"];
function caretPoint(textarea) {
  const style = getComputedStyle(textarea);
  const mirror = document.createElement("div");
  for (const property of MIRRORED) mirror.style[property] = style[property];
  const wraps = style.whiteSpace !== "pre" && textarea.getAttribute("wrap") !== "off";
  Object.assign(mirror.style, { position: "absolute", visibility: "hidden", left: "-9999px", top: "0", overflow: "hidden", width: `${textarea.offsetWidth}px`,
    whiteSpace: wraps ? "pre-wrap" : "pre", overflowWrap: wraps ? "break-word" : "normal" });
  mirror.textContent = textarea.value.slice(0, textarea.selectionStart);
  const marker = document.createElement("span");
  marker.textContent = "\u200b";
  mirror.append(marker);
  document.body.append(mirror);
  const rect = textarea.getBoundingClientRect();
  const scaleX = textarea.offsetWidth ? rect.width / textarea.offsetWidth : 1, scaleY = textarea.offsetHeight ? rect.height / textarea.offsetHeight : 1;
  const point = { x: rect.left + (marker.offsetLeft - textarea.scrollLeft) * scaleX, y: rect.top + (marker.offsetTop - textarea.scrollTop + marker.offsetHeight) * scaleY + 2,
    lineHeight: marker.offsetHeight * scaleY };
  mirror.remove();
  return point;
}
let popupRequest = 0; // Counts popup updates: one still waiting for the list when a newer keystroke (or a close) came is dropped.
function closePopup() {
  popupRequest++;
  popup.element?.remove();
  popup.element = null;
  popup.textarea = null;
}
function renderPopup() {
  popup.element.replaceChildren(...popup.items.map((item, index) => {
    const row = element("div", { class: (index === popup.index ? "on " : "") + (item.browse ? "browse" : "") },
      `${item.favorite ? "★ " : ""}${item.label}`, ...(item.hint != null ? [element("span", { class: "n" }, `${item.hint}`)] : []));
    row.addEventListener("mousedown", (event) => { event.preventDefault(); background(accept(index)); });
    return row;
  }));
  popup.element.children[popup.index]?.scrollIntoView({ block: "nearest" });
}
// Wildcards: what is typed after the last "__" (not the first: in "__hair__ __col" it is "col"), in letters and digits of every script like the
// server's \w.
addCompletionSource((before) => {
  const opening = before.lastIndexOf("__");
  const typedText = opening < 0 ? "" : before.slice(opening + 2);
  if (before.split("__").length % 2 !== 0 || opening < 0 || !/^[\p{L}\p{N}_\-./*? ]*$/u.test(typedText)) return null;
  const typed = typedText.toLowerCase();
  const items = wildcardList().then(({ files }) => {
    const entries = [...files.map((file) => ({ token: file.name, hint: file.lines, favorite: !!file.favorite })), ...folderNames(files).map((folder) => ({ token: `${folder}/*` }))];
    const found = entries.filter((entry) => entry.token.toLowerCase().includes(typed)) // Names that start with what is typed first, then ★ favorites.
      .sort((a, b) => (b.token.toLowerCase().startsWith(typed) - a.token.toLowerCase().startsWith(typed)) || (!!b.favorite - !!a.favorite) || a.token.localeCompare(b.token)).slice(0, 12);
    return [...found.map((entry) => ({ ...entry, label: `__${entry.token}__`, insert: `__${entry.token}__` })), { browse: true, label: "📂 Browse wildcards…" }];
  });
  return { start: opening, items, skip: "__" }; // Typed closing underscores are replaced too.
});
// LoRAs: after "<lora:" (or "<lyco:"), the LoRA files that contain what is typed, put in as <lora:folder/name:1>.
let loraFiles = null, loraTime = 0;
async function loraList() {
  if (!loraFiles || Date.now() - loraTime > 30000) {
    try { loraFiles = await (await api.fetchApi("/models/loras")).json(); } catch { loraFiles ??= []; }
    loraTime = Date.now();
  }
  return Array.isArray(loraFiles) ? loraFiles : [];
}
addCompletionSource((before) => {
  const match = /<\s*(lora|lyco)\s*:([^:<>\n]*)$/i.exec(before);
  if (!match) return null;
  const typed = match[2].trim().toLowerCase();
  const items = loraList().then((files) => files.map((file) => file.replace(/\\/g, "/").replace(/\.[^./]+$/, ""))
    .filter((name) => name.toLowerCase().includes(typed))
    .sort((a, b) => (b.toLowerCase().split("/").pop().startsWith(typed) - a.toLowerCase().split("/").pop().startsWith(typed)) || a.localeCompare(b)).slice(0, 15)
    .map((name) => ({ label: name, hint: "LoRA", insert: `<${match[1].toLowerCase()}:${name}:1>` })));
  return { start: match.index, items, skip: ">" };
});
// The Wildcard Browser's editor has the autocomplete too (tags, __wildcards__, <lora:): a line of a wildcard file is a prompt.
const isEditor = (textarea) => textarea.classList?.contains("dfwc-editor");
async function updatePopup(textarea) {
  const request = ++popupRequest;
  if (!isEditor(textarea) && !fieldOf(textarea)) return closePopup();
  const before = textarea.value.slice(0, textarea.selectionStart);
  const found = sources.map((source) => source(before)).find(Boolean);
  if (!found) return closePopup();
  const items = (await found.items).filter((item) => !(item.browse && isEditor(textarea))); // The browser is open already.
  if (request !== popupRequest) return; // Typed on (or closed) meanwhile: the newer update shows the popup, for the text as it is now.
  if (!items.length) return closePopup();
  popup.items = items;
  popup.index = 0;
  popup.start = found.start;
  popup.skip = found.skip ?? null;
  popup.textarea = textarea;
  if (!popup.element) {
    addStyle();
    popup.element = element("div", { class: "dfwc-pop" });
    document.body.append(popup.element);
  }
  renderPopup();
  // Under the caret's line; above it when there is no room below (near the bottom of the window).
  const point = caretPoint(textarea), height = popup.element.offsetHeight, line = point.lineHeight;
  const top = point.y + height > innerHeight - 4 && point.y - line - height - 4 >= 0 ? point.y - line - height - 4 : Math.min(point.y, innerHeight - height - 4);
  Object.assign(popup.element.style, { left: `${Math.max(0, Math.min(point.x, innerWidth - popup.element.offsetWidth - 4))}px`, top: `${Math.max(0, top)}px` });
}
function accept(index) {
  const item = popup.items[index];
  const textarea = popup.textarea;
  const skip = popup.skip; // Read before closePopup.
  if (!item || !textarea) return closePopup();
  if (isEditor(textarea)) { // Put in the editor's text, as typed (its line numbers and Save • follow the input event).
    const start = popup.start, end = textarea.selectionStart;
    const after = skip && textarea.value.slice(end).startsWith(skip) ? skip.length : 0;
    closePopup();
    textarea.value = textarea.value.slice(0, start) + item.insert + textarea.value.slice(end + after);
    textarea.setSelectionRange(start + item.insert.length, start + item.insert.length);
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
    return textarea.focus();
  }
  const field = fieldOf(textarea);
  closePopup();
  if (!field) return;
  if (item.browse) {
    lastCursor.set(field.node, { name: field.name, start: textarea.selectionStart, end: textarea.selectionEnd });
    return openBrowser(field.node);
  }
  const start = popup.start, end = textarea.selectionStart;
  const after = skip && textarea.value.slice(end).startsWith(skip) ? skip.length : 0;
  setField(field.node, field.name, textarea.value.slice(0, start) + item.insert + textarea.value.slice(end + after), start + item.insert.length);
}
document.addEventListener("input", (event) => { if (event.target?.tagName === "TEXTAREA" && event.isTrusted) background(updatePopup(event.target)); }, true);
document.addEventListener("keydown", (event) => {
  if (!popup.element || event.target !== popup.textarea) return;
  const keys = { ArrowDown: 1, ArrowUp: -1 };
  if (event.key in keys) popup.index = (popup.index + keys[event.key] + popup.items.length) % popup.items.length, renderPopup();
  else if (event.key === "Enter" || event.key === "Tab") background(accept(popup.index));
  else if (event.key === "Escape") closePopup();
  else return;
  event.preventDefault();
  event.stopImmediatePropagation(); // Not the Wildcard Browser's own keys too (Escape closing it).
}, true);
document.addEventListener("focusout", (event) => { if (event.target === popup.textarea) setTimeout(closePopup, 150); rememberCursor(event); }, true);
for (const type of ["keyup", "mouseup", "focusin"]) document.addEventListener(type, rememberCursor, true);

// Folders open in the Wildcard Browser, kept between openings (and reloads) in this browser. Folders start closed; a search opens them all.
const OPEN_KEY = "diceforge.wildcards.open";
const CARDS_KEY = "diceforge.wildcards.cards";
function openFolders() {
  try { return new Set(JSON.parse(localStorage.getItem(OPEN_KEY)) || []); } catch { return new Set(); }
}
function keepOpenFolders(folders) {
  try { localStorage.setItem(OPEN_KEY, JSON.stringify([...folders])); } catch { /* Private mode or no storage: open only for this visit. */ }
}

// Wildcard Browser: folder tree (click a folder to open or close it) with search, "+ Add" for files (__name__) and folders (__folder/*__), and the selected file's editor: create, save
// (button or Ctrl+S; • marks unsaved changes), rename, move to another folder (Move, or drag a file onto a folder) and delete.
async function openBrowser(node) {
  addStyle();
  addHighlightStyle();
  const search = element("input", { placeholder: "Search wildcards (names and lines)…" });
  const tree = element("div", { class: "tree" });
  const title = element("div", { class: "muted" }, "Select a file to see and edit its lines, one option per line (# starts a comment).");
  const editor = element("textarea", { class: "src dfwc-editor", placeholder: "One option per line", wrap: "off", spellcheck: "false" });
  // The text is drawn, with its syntax colored as in the prompt fields, by a layer behind the editor, whose own text is transparent (it keeps
  // the caret, selection and editing). The layer also draws the lines under the rows and the caret's line.
  const highlight = element("div", { class: "dfhl hl", "aria-hidden": "true" });
  const paint = () => {
    const text = editor.value;
    if (highlightEnabled() && text.length <= 300000) highlight.innerHTML = highlightWildcardFile(text, knownWildcards()); // A huge file: plain.
    else highlight.textContent = text + "\n";
    highlight.scrollTop = editor.scrollTop;
    highlight.scrollLeft = editor.scrollLeft;
  };
  // Line numbers next to the editor, as in a code editor, scrolled with it; lines don't wrap, so each number stays next to its line.
  const lines = element("div", { class: "lines", "aria-hidden": "true" }, "1");
  const numberLines = () => {
    const count = editor.value.split("\n").length;
    if (lines.dataset.count !== String(count)) {
      lines.dataset.count = String(count);
      lines.textContent = Array.from({ length: count }, (_, index) => index + 1).join("\n");
      lines.style.width = `${String(count).length}ch`;
    }
    lines.scrollTop = editor.scrollTop;
    paint();
  };
  editor.addEventListener("input", numberLines);
  editor.addEventListener("scroll", () => {
    lines.scrollTop = highlight.scrollTop = editor.scrollTop;
    highlight.scrollLeft = editor.scrollLeft;
  });
  // The line with the caret is highlighted, in the text and its number (a background row, scrolled with the text).
  const code = element("div", { class: "code" }, lines, element("div", { class: "text" }, highlight, editor));
  const markCurrentLine = () => {
    let line = 0;
    for (let at = editor.value.indexOf("\n"); at !== -1 && at < editor.selectionStart; at = editor.value.indexOf("\n", at + 1)) line++;
    code.style.setProperty("--current-line", `${6 + 20 * line}px`);
  };
  const onSelection = () => { if (document.activeElement === editor) markCurrentLine(); };
  document.addEventListener("selectionchange", onSelection);
  for (const type of ["input", "click", "keyup", "focus"]) editor.addEventListener(type, markCurrentLine);
  // + next to a line's number puts that line in the prompt (without its 3:: weight), where the cursor was in the node's fields.
  const lineAdd = element("button", { class: "line-add", hidden: true, title: "Add this line to the prompt" }, "+");
  code.append(lineAdd);
  const lineText = (index) => (editor.value.split("\n")[index] ?? "").trim().replace(/^\d+(?:\.\d+)?::/, "").trim();
  code.addEventListener("mousemove", (event) => {
    if (event.target === lineAdd) return;
    const index = Math.floor((event.clientY - code.getBoundingClientRect().top - 6 + editor.scrollTop) / 20);
    const text = lineText(index);
    lineAdd.hidden = !text || text.startsWith("#");
    lineAdd.dataset.line = String(index);
    lineAdd.style.top = `${6 + 20 * index - editor.scrollTop + 1}px`;
  });
  code.addEventListener("mouseleave", () => { lineAdd.hidden = true; });
  editor.addEventListener("scroll", () => { lineAdd.hidden = true; });
  lineAdd.addEventListener("click", () => {
    const text = lineText(Number(lineAdd.dataset.line));
    if (!text) return;
    const field = insertIntoNode(node, text);
    say(`Added line ${Number(lineAdd.dataset.line) + 1} to ${field}.`);
  });
  const status = element("div", { class: "status" });
  const save = element("button", { class: "save" }, "Save");
  const rename = element("button", { class: "rename", disabled: true }, "Rename");
  const move = element("button", { class: "move", disabled: true, title: "Move the file to another folder (or drag it onto a folder in the tree)" }, "⇄ Move");
  const remove = element("button", { class: "delete", disabled: true }, "Delete");
  const convertButton = element("button", { class: "convert", disabled: true }, "→ yaml");
  let selected = null, saved = "", selectedYaml = false;
  const showDirty = () => { save.textContent = selected && !editor.readOnly && editor.value !== saved ? "Save •" : "Save"; };
  editor.addEventListener("input", showDirty);
  editor.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); event.stopPropagation(); save.click(); }
  });
  const back = element("div", { class: "dfwc-back" });
  const dialog = element("div", { class: "dfwc" }), editPane = element("div", { class: "edit" });
  const close = () => {
    // Opens again where it was: the search, ★ Favorites, the open file (its unsaved changes too, if the file stays the same), the scrolling.
    const dirty = selected && !editor.readOnly && editor.value !== saved;
    remember("wildcards", { search: search.value, favorites: onlyFavorites, cardFolder, selected, caret: editor.selectionStart, tree: tree.scrollTop,
      editor: editor.scrollTop, cards: cards.querySelector(".grid")?.scrollTop ?? 0, ...(dirty ? { draft: editor.value, saved } : {}) });
    stopSize();
    closeMenu();
    back.remove();
    document.removeEventListener("keydown", onKey, true);
    document.removeEventListener("selectionchange", onSelection);
  };
  const onKey = (event) => {
    if (document.querySelector(".dfmv-back")) return; // The folder picker has the keys (and closes first).
    if (event.key === "Escape") {
      event.stopPropagation();
      if (menuOpen()) closeMenu(); // Then a right-click menu, then the browser.
      else close();
      return;
    }
    if (menuOpen() || slashToSearch(event, search)) return;
    treeKeys(event);
  };
  // The keyboard in the tree (from the search box too): ↑ ↓ pick a file, Enter puts it in the prompt, Shift+Enter opens it, F2 renames it,
  // Delete deletes it (↶ Undo brings it back), the menu key or Shift+F10 opens its menu. The editor keeps its own keys.
  function treeKeys(event) {
    if (event.target === editor || (typingIn(event) && event.target !== search)) return;
    const rows = [...tree.querySelectorAll(".row[data-name]")].filter((row) => row.offsetParent);
    const file = () => (listCache?.files ?? []).find((item) => item.name === tree.querySelector(".row.cursor[data-name]")?.dataset.name);
    const key = event.key, action = {
      ArrowDown: () => moveCursor(rows, 1), ArrowUp: () => moveCursor(rows, -1),
      Enter: () => file() && (event.shiftKey ? background(open(file().name)) : add(file().name)),
      F2: () => file() && !file().yaml && background(renameFile(file().name)),
      Delete: () => file() && !file().yaml && event.target !== search && background(deleteFile(file().name)),
      ContextMenu: () => file() && menuAt(tree.querySelector(".row.cursor"), fileItems(file())),
    }[key === "F10" && event.shiftKey ? "ContextMenu" : key];
    if (!action || (key === "Enter" && !file())) return;
    event.preventDefault();
    event.stopPropagation();
    action();
  }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  // A message; after a rename, a move or a delete, with ↶ Undo (until the next message), and maybe one more thing to do ([label, action]).
  const say = (text, undo, more) => {
    status.replaceChildren(text, ...(undo ? [element("button", { class: "undo", title: "Undo it", onclick: () => background(undo()) }, "↶ Undo")] : []),
      ...(more ? [element("button", { class: "more-action", onclick: () => background(Promise.resolve().then(more[1])) }, more[0])] : []));
  };
  const add = (token) => { const field = insertIntoNode(node, `__${token}__`); say(`Added __${token}__ to ${field}.`); };
  async function open(name) {
    const response = await api.fetchApi(`/diceforge/wildcards/file?name=${encodeURIComponent(name)}`);
    if (!response.ok) return say(await response.text());
    const file = await response.json();
    selected = name;
    const parts = name.split("/").slice(0, -1); // The file's folders open, so it shows in the tree.
    parts.forEach((_, index) => opened.add(parts.slice(0, index + 1).join("/")));
    keepOpenFolders(opened);
    title.replaceChildren(element("b", {}, `__${name}__`), " ", element("span", { class: "muted" }, file.path));
    editor.value = saved = file.text;
    editor.scrollTop = 0;
    editor.setSelectionRange(0, 0);
    numberLines();
    markCurrentLine();
    editor.readOnly = !!file.readonly; // A yaml wildcard is one key of a yaml file: edited in that file.
    code.classList.toggle("readonly", editor.readOnly);
    save.disabled = rename.disabled = move.disabled = remove.disabled = !!file.readonly;
    selectedYaml = !!file.readonly;
    convertButton.disabled = false;
    convertButton.textContent = selectedYaml ? "→ txt" : "→ yaml";
    convertButton.title = selectedYaml ? "Turn its yaml file into txt files, one per key (the names stay the same)" : `Turn ${name}.txt into ${name.split("/").pop()}.yaml (the name stays the same)`;
    showDirty();
    say(file.readonly ? "From a yaml file: read-only here, edit the yaml file to change it." : "");
    draw();
  }
  save.addEventListener("click", async () => {
    if (!selected) return say("Select or create a file first.");
    const text = editor.value;
    const response = await api.fetchApi("/diceforge/wildcards/file", { method: "POST", body: JSON.stringify({ name: selected, text }) });
    if (response.ok) saved = text;
    say(response.ok ? `Saved ${selected}.txt.` : await response.text());
    showDirty();
    await wildcardList(true);
    draw();
  });
  async function renameTo(name, to, moved) {
    const response = await api.fetchApi("/diceforge/wildcards/rename", { method: "POST", body: JSON.stringify({ name, to }) });
    if (!response.ok) return say(await response.text());
    const result = await response.json();
    await wildcardList(true);
    if (name === selected) { // The open file: it stays open under its new name, with its unsaved changes.
      const edited = editor.value !== saved ? editor.value : null;
      await open(result.to);
      if (edited != null) editor.value = edited, showDirty();
      numberLines();
      markCurrentLine();
    } else draw();
    say(`${moved ? "Moved" : "Renamed"} ${result.renamed} to ${result.to}. Prompts that use __${result.renamed}__ need the new name.`,
      () => renameTo(result.to, result.renamed, moved), // Undo: back to its old name and folder.
      ["🔁 Update the wildcard files that use it", () => openReplace(`__${result.renamed}__`, `__${result.to}__`)]);
  }
  async function renameFile(name) {
    const to = prompt("New name (folders with /, for example hair/color):", name)?.trim();
    if (to && to !== name) await renameTo(name, to, false);
  }
  rename.addEventListener("click", () => { if (selected) background(renameFile(selected)); });
  // Move: the same file name in another folder ("" for the top folder), picked in the folder picker or by dropping the file on a folder.
  async function moveFile(name, to) {
    const parts = name.split("/"), from = parts.slice(0, -1).join("/");
    const destination = to ?? await pickFolder({ title: `Move ${parts.at(-1)} to…`, folders: folderNames(listCache?.files ?? []), current: from });
    if (destination == null || destination === from) return;
    await renameTo(name, `${destination ? `${destination}/` : ""}${parts.at(-1)}`, true);
  }
  move.addEventListener("click", () => { if (selected) background(moveFile(selected)); });
  async function deleteFile(name) {
    if (!confirm(`Delete the wildcard file ${name}.txt? (↶ Undo brings it back.)`)) return;
    const response = await api.fetchApi(`/diceforge/wildcards/file?name=${encodeURIComponent(name)}`, { method: "DELETE" });
    if (!response.ok) return say(await response.text());
    if (name === selected) { // The open file: the editor empties.
      selected = null;
      editor.value = saved = "";
      numberLines();
      markCurrentLine();
      editor.readOnly = false;
      code.classList.remove("readonly");
      rename.disabled = move.disabled = remove.disabled = convertButton.disabled = true;
      showDirty();
      title.replaceChildren("Select a file to see and edit its lines, one option per line (# starts a comment).");
    }
    const { undo } = await response.json();
    await wildcardList(true);
    draw();
    say(`Deleted ${name}.txt.`, () => restore(undo));
  }
  remove.addEventListener("click", () => { if (selected) background(deleteFile(selected)); });
  // Undo a delete: the file comes back where it was (from the server's trash), with its star, and opens.
  async function restore(id) {
    const response = await api.fetchApi("/diceforge/wildcards/restore", { method: "POST", body: JSON.stringify({ id }) });
    if (!response.ok) return say(await response.text());
    const result = await response.json();
    await wildcardList(true);
    await open(result.restored);
    say(`${result.restored} is back.`);
  }
  // Export a folder (or every wildcard) as a zip, which Import zip takes back: to share a card pack or keep a copy.
  function exportZip(folder = "") {
    const link = element("a", { href: api.apiURL(`/diceforge/wildcards/export${folder ? `?folder=${encodeURIComponent(folder)}` : ""}`), download: "" });
    document.body.append(link);
    link.click();
    link.remove();
    say(`Downloading ${folder ? `the folder ${folder}` : "every wildcard"} as a zip.`);
  }
  const exportButton = element("button", { class: "export", title: "Download every wildcard as a zip (⇩ zip on a folder downloads that folder)", onclick: () => exportZip() }, "⇩ Export zip");
  // txt ⇄ yaml: a txt file or a folder of them becomes one yaml file (hair/ -> hair.yaml), a yaml file becomes one txt file per key. The
  // wildcard names stay the same, so prompts keep working; card pictures stay where they are.
  async function convert(name, to) {
    if (selected && editor.value !== saved && (selected === name || selected.startsWith(`${name}/`))) return say("Save (or undo) your changes first.");
    const what = to === "yaml" ? `the txt wildcards ${name} into ${name.split("/").pop()}.yaml` : `the yaml file of ${name} into txt files, one per key`;
    if (!confirm(`Convert ${what}? The wildcard names stay the same.`)) return;
    const response = await api.fetchApi("/diceforge/wildcards/convert", { method: "POST", body: JSON.stringify({ name, to }) });
    if (!response.ok) return say(await response.text());
    const result = await response.json();
    await wildcardList(true);
    if (selected && result.names.includes(selected)) await open(selected);
    else draw();
    say(to === "yaml" ? `Converted ${result.names.length} wildcard${result.names.length === 1 ? "" : "s"} into ${result.path}.`
      : `Converted ${result.removed.join(", ")} into ${result.names.length} txt file${result.names.length === 1 ? "" : "s"}.`);
  }
  convertButton.addEventListener("click", () => { if (selected) background(convert(selected, selectedYaml ? "txt" : "yaml")); });
  // ⇪ Import zip: a card pack or any zip of wildcards into the wildcards folder, with its paths (files already there are kept). A zip dropped on
  // the browser does the same.
  async function importZip(file) {
    if (!file) return;
    say(`Importing ${file.name}…`);
    const response = await api.fetchApi("/diceforge/wildcards/import", { method: "POST", body: file });
    if (!response.ok) return say(await response.text());
    const result = await response.json();
    await wildcardList(true);
    draw();
    say(`Imported ${result.imported.length} file${result.imported.length === 1 ? "" : "s"} from ${file.name}` +
      (result.skipped.length ? `; ${result.skipped.length} already there, kept as they were` : "") + (result.left_out.length ? `; ${result.left_out.length} not wildcards or pictures, left out` : "") + ".");
  }
  const importButton = element("button", { class: "import", title: "Import a zip of wildcards (a card pack: yaml files and their pictures); or drop the zip on this window", onclick: () => {
    const input = element("input", { type: "file", accept: ".zip,application/zip" });
    input.addEventListener("change", () => background(importZip(input.files?.[0])));
    input.click();
  } }, "⇪ Import zip");
  async function createFile(suggested) {
    const name = prompt("New wildcard file name (folders with /, for example hair/color):", suggested);
    if (!name) return;
    const response = await api.fetchApi("/diceforge/wildcards/file", { method: "POST", body: JSON.stringify({ name, text: "", create: true }) });
    if (!response.ok) return say(await response.text());
    await wildcardList(true);
    await open((await response.json()).saved);
  }
  const create = element("button", { onclick: () => background(createFile(search.value.trim())) }, "+ New file");
  const opened = openFolders();
  const toggle = (path, open = !opened.has(path)) => {
    if (open) opened.add(path); else opened.delete(path);
    keepOpenFolders(opened);
    draw();
  };
  const expandAll = element("button", { class: "open-all", title: "Open every folder", onclick: () => {
    for (const folder of folderNames(listCache?.files ?? [])) opened.add(folder);
    keepOpenFolders(opened);
    draw();
  } }, "Expand all");
  const collapseAll = element("button", { class: "close-all", title: "Close every folder", onclick: () => { opened.clear(); keepOpenFolders(opened); draw(); } }, "Collapse all");
  // ★ Favorites: a star on a file, kept on the server (it follows renames and moves); the toolbar button shows only them.
  // ⚠ Broken: only the files that use a wildcard no file answers (a typo, a renamed file); shown when there are some.
  let onlyBroken = false;
  const brokenButton = element("button", { class: "only-broken", title: "Show only the files that use wildcards that don't exist (⚠ on the row names them)", onclick: () => {
    onlyBroken = !onlyBroken;
    brokenButton.classList.toggle("on", onlyBroken);
    draw();
  } }, "⚠ Broken");
  let onlyFavorites = false;
  const favoritesButton = element("button", { class: "only-favorites", title: "Show only your favorites (☆ on a file)", onclick: () => {
    onlyFavorites = !onlyFavorites;
    favoritesButton.classList.toggle("on", onlyFavorites);
    draw();
  } }, "★ Favorites");
  // Two ways to see the wildcards: 📄 Lines (the tree and the editor) and 🃏 Cards (a folder's wildcards as cards, with their pictures: a yaml card
  // pack's POSES/sitting.jpeg next to POSES.yaml; + Add inserts one card, 🎲 a random card of the folder). The mode is remembered.
  let cardsMode = false, cardFolder = null;
  try { cardsMode = localStorage.getItem(CARDS_KEY) === "1"; } catch { /* No storage: lines. */ }
  const modeButton = element("button", { class: "mode", title: "Show the wildcards as cards with their pictures (yaml card packs), or as lines with the editor" });
  const cards = element("div", { class: "cards" });
  const setMode = (on) => {
    cardsMode = on;
    try { localStorage.setItem(CARDS_KEY, on ? "1" : "0"); } catch { /* No storage: for this visit. */ }
    draw();
  };
  modeButton.addEventListener("click", () => setMode(!cardsMode));
  let pictureVersion = Date.now(); // Changes with a new picture: the browser doesn't show the old one from its cache.
  const pictureURL = (name) => api.apiURL(`/diceforge/wildcards/picture?name=${encodeURIComponent(name)}&v=${pictureVersion}`);
  // A card's example picture (yaml cards): 🖼 picks a file, or drop a picture on the card; ✕ removes it. Saved next to the yaml file.
  async function setPicture(name, file) {
    if (!file) return;
    const response = await api.fetchApi(`/diceforge/wildcards/picture?name=${encodeURIComponent(name)}`, { method: "POST", body: file });
    if (!response.ok) return say(await response.text());
    pictureVersion = Date.now();
    await wildcardList(true);
    say(`New picture for __${name}__.`);
    draw();
  }
  async function removePicture(name) {
    if (!confirm(`Remove the picture of __${name}__?`)) return;
    const response = await api.fetchApi(`/diceforge/wildcards/picture?name=${encodeURIComponent(name)}`, { method: "DELETE" });
    if (!response.ok) return say(await response.text());
    await wildcardList(true);
    say(`Removed the picture of __${name}__.`);
    draw();
  }
  const pickPicture = (name) => {
    const input = element("input", { type: "file", accept: "image/png,image/jpeg,image/webp,image/gif" });
    input.addEventListener("change", () => background(setPicture(name, input.files?.[0])));
    input.click();
  };
  function card(file) {
    const pic = element("div", { class: "pic", title: file.preview.join("\n") });
    if (file.picture) {
      const img = element("img", { src: pictureURL(file.name), loading: "lazy", alt: file.name });
      img.addEventListener("error", () => img.replaceWith(element("span", { class: "none" }, file.preview[0] ?? "")));
      pic.append(img);
    } else pic.append(element("span", { class: "none" }, file.preview[0] ?? "(empty)"));
    const pictureButtons = file.yaml ? [
      element("button", { class: "picture", title: "Choose an example picture for this card (or drop one on the card)", onclick: () => pickPicture(file.name) }, "🖼"),
      ...(file.picture ? [element("button", { class: "no-picture", title: "Remove the picture", onclick: () => background(removePicture(file.name)) }, "✕")] : []),
    ] : [];
    const box = element("div", { class: "card", "data-name": file.name }, pic,
      element("div", { class: "info" },
        element("span", { class: "title", title: "Open it in the lines view", onclick: () => { setMode(false); background(open(file.name)); } }, file.name.split("/").pop()),
        element("span", { class: "line", title: file.preview.join("\n") }, file.lines > 1 ? `${file.lines} lines: ${file.preview.join(" · ")}` : file.preview[0] ?? ""),
        element("div", { class: "actions" },
          element("button", { class: "fav" + (file.favorite ? " on" : ""), title: file.favorite ? "A favorite: click to remove the star" : "Add to favorites",
            onclick: () => background(setFavorite(file.name, !file.favorite)) }, file.favorite ? "★" : "☆"),
          ...pictureButtons,
          element("button", { class: "add", title: `Insert __${file.name}__`, onclick: () => add(file.name) }, "+ Add"))));
    if (file.yaml) { // A picture file dropped on the card becomes its picture.
      box.addEventListener("dragover", (event) => { if (event.dataTransfer?.types?.includes("Files")) { event.preventDefault(); box.classList.add("drop"); } });
      box.addEventListener("dragleave", () => box.classList.remove("drop"));
      box.addEventListener("drop", (event) => {
        if (!event.dataTransfer?.files?.length) return;
        event.preventDefault();
        box.classList.remove("drop");
        background(setPicture(file.name, event.dataTransfer.files[0]));
      });
    }
    return box;
  }
  function drawCards(shown) {
    if (cardFolder == null) { // The first time: the folder of the first wildcard with a picture.
      const first = shown.find((file) => file.picture);
      cardFolder = first ? first.name.split("/").slice(0, -1).join("/") : "";
    }
    const inFolder = shown.filter((file) => !cardFolder || file.name.startsWith(`${cardFolder}/`));
    const limit = 400; // A huge folder: the first ones, the search narrows it.
    cards.replaceChildren(
      element("div", { class: "cards-head" }, element("b", {}, `📁 ${cardFolder || "All wildcards"}`),
        element("span", { class: "muted" }, `${inFolder.length} card${inFolder.length === 1 ? "" : "s"} · click a folder in the tree to see its cards`),
        ...(cardFolder ? [element("button", { class: "add random", title: `Insert __${cardFolder}/*__: a random card of the folder each run`, onclick: () => add(`${cardFolder}/*`) }, "🎲 + Add random")] : [])),
      element("div", { class: "grid" }, ...(inFolder.length ? inFolder.slice(0, limit).map(card) : [element("div", { class: "muted" }, "No wildcards here.")]),
        ...(inFolder.length > limit ? [element("div", { class: "muted" }, `${inFolder.length - limit} more: search to narrow them.`)] : [])));
  }
  async function setFavorite(name, favorite) {
    const response = await api.fetchApi("/diceforge/wildcards/favorite", { method: "POST", body: JSON.stringify({ name, favorite }) });
    if (!response.ok) return say(await response.text());
    await wildcardList(true); // The autocomplete gets the star too.
    say(favorite ? `__${name}__ is a favorite.` : `__${name}__ is no longer a favorite.`);
    draw();
  }
  // Right-click on a file or a folder (or its ⋯): everything that can be done with it, so the rows keep only ☆ and + Add.
  function fileItems(file) {
    return [
      ["📝 Open", () => open(file.name)],
      [`＋ Add __${file.name}__`, () => add(file.name)],
      ["🎲 Preview picks", () => previewPicks(file.name), "What a run would put in for it: a few random picks"],
      [file.favorite ? "☆ Remove the star" : "★ Add to favorites", () => setFavorite(file.name, !file.favorite)],
      "-",
      ...(file.yaml ? [["→ txt files", () => convert(file.name, "txt"), "Turn its yaml file into txt files, one per key (the names stay the same)"]]
        : [["✎ Rename…", () => renameFile(file.name)], ["⇄ Move…", () => moveFile(file.name)],
          ["→ yaml", () => convert(file.name, "yaml"), `Turn ${file.name}.txt into ${file.name.split("/").pop()}.yaml (the name stays the same)`],
          ["🧹 Remove duplicates and empty lines", () => cleanUp(file.name, false), "In the editor: Save keeps it"],
          ["🔤 Sort lines A→Z (and clean up)", () => cleanUp(file.name, true), "Sorted by the text (a line's N:: weight left aside); comments at the top stay there. In the editor: Save keeps it"], "-",
          ["🗑 Delete", () => deleteFile(file.name)]]),
    ];
  }
  function folderItems(path) {
    const inside = (listCache?.files ?? []).filter((file) => file.name.startsWith(`${path}/`));
    return [
      [`＋ Add __${path}/*__`, () => add(`${path}/*`)],
      ["🎲 Preview picks", () => previewPicks(path, true), "What a run would put in for __folder/*__: a few random picks"],
      [opened.has(path) ? "▸ Close the folder" : "▾ Open the folder", () => toggle(path)],
      "-",
      ["＋ New file here…", () => createFile(`${path}/`)],
      ["⇩ Export zip", () => exportZip(path), "Download the folder as a zip (with a card pack's yaml file)"],
      ...(inside.some((file) => !file.yaml) ? [["→ yaml", () => convert(path, "yaml"), `Turn the folder's txt files into ${path.split("/").pop()}.yaml (the names stay the same)`]] : []),
      ...(inside.some((file) => file.yaml) ? [["→ txt", () => convert(path, "txt"), "Turn the folder's yaml file into txt files, one per key (the names stay the same)"]] : []),
    ];
  }
  // 🎲 Preview picks: what a run would put in for a wildcard (or __folder/*__), a few times, each with + Add to use that very text.
  // 🧹 Clean up a file in the editor: duplicate and empty lines go (and, sorting, the lines go A→Z by their text, a weight like 3:: left aside);
  // the comment lines at its top stay there. Not saved: Save keeps it, reopening the file drops it.
  async function cleanUp(name, sort) {
    if (selected !== name) await open(name);
    if (selected !== name || editor.readOnly) return;
    const result = cleanLines(editor.value, sort);
    editor.value = result.text;
    numberLines();
    markCurrentLine();
    showDirty();
    say(`${name}: ${result.duplicates} duplicate${result.duplicates === 1 ? "" : "s"} and ${result.empty} empty line${result.empty === 1 ? "" : "s"} dropped${sort ? ", sorted A→Z" : ""}. Save keeps it.`);
  }
  // 🔁 Find and replace in every txt wildcard file: a preview of what changes first, then Replace (after a rename: the old name in the files
  // that use it). Yaml files are named, not changed.
  const replacePanel = element("div", { class: "replace", hidden: "" });
  const findInput = element("input", { class: "find", placeholder: "Find (as written, case and all)" });
  const replaceInput = element("input", { class: "with", placeholder: "Replace with" });
  const replaceResults = element("div", { class: "results" });
  async function replaceCall(apply) {
    const response = await api.fetchApi("/diceforge/wildcards/replace", { method: "POST", body: JSON.stringify({ find: findInput.value, replace: replaceInput.value, apply }) });
    if (!response.ok) return say(await response.text());
    return response.json();
  }
  async function previewReplace() {
    const result = await replaceCall(false);
    if (!result) return;
    const count = result.files.reduce((sum, file) => sum + file.count, 0);
    replaceResults.replaceChildren(
      element("div", { class: "muted" }, result.files.length ? `${count} in ${result.files.length} file${result.files.length === 1 ? "" : "s"}:` : "Not in any txt file.",
        ...(result.in_yaml.length ? [` Also in yaml wildcards (edit their yaml files): ${result.in_yaml.join(", ")}.`] : [])),
      ...result.files.map((file) => element("div", { class: "change" }, element("b", {}, `${file.name} ×${file.count}`),
        element("span", { class: "before" }, file.line), element("span", { class: "after" }, file.after))),
      ...(result.files.length ? [element("button", { class: "apply", onclick: () => background(applyReplace(result.files.length)) }, `Replace in ${result.files.length} file${result.files.length === 1 ? "" : "s"}`)] : []));
  }
  async function applyReplace(fileCount) {
    if (selected && editor.value !== saved) return say("Save (or undo) the open file's changes first: the replace would change it under you.");
    if (!confirm(`Replace “${findInput.value}” with “${replaceInput.value}” in ${fileCount} file${fileCount === 1 ? "" : "s"}?`)) return;
    const result = await replaceCall(true);
    if (!result) return;
    await wildcardList(true);
    if (selected && result.files.some((file) => file.name === selected)) await open(selected); // The open file as it is now.
    draw();
    replaceResults.replaceChildren();
    say(`Replaced “${findInput.value}” with “${replaceInput.value}” in ${result.files.length} file${result.files.length === 1 ? "" : "s"}.`);
  }
  async function openReplace(find = findInput.value, replacement = replaceInput.value) {
    findInput.value = find;
    replaceInput.value = replacement;
    replacePanel.hidden = false;
    replaceResults.replaceChildren();
    if (find) await previewReplace();
    else findInput.focus();
  }
  for (const input of [findInput, replaceInput]) input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); background(previewReplace()); } });
  replacePanel.append(element("div", { class: "replace-head" }, element("b", {}, "🔁"), findInput, element("span", {}, "→"), replaceInput,
    element("button", { class: "preview", onclick: () => background(previewReplace()) }, "Preview"),
    element("button", { class: "close-replace", title: "Close", onclick: () => { replacePanel.hidden = true; } }, "✕")), replaceResults);
  const replaceButton = element("button", { class: "replace-open", title: "Find and replace in every wildcard file (a preview first)", onclick: () => background(openReplace()) }, "🔁 Replace");
  const picks = element("div", { class: "picks", hidden: "" });
  async function previewPicks(name, folder = false) {
    const response = await api.fetchApi(`/diceforge/wildcards/preview?name=${encodeURIComponent(name)}${folder ? "&folder=1" : ""}&count=5`);
    if (!response.ok) return say(await response.text());
    const result = await response.json();
    picks.hidden = false;
    picks.replaceChildren(
      element("div", { class: "picks-head" }, element("b", {}, `🎲 __${result.token}__`), element("span", { class: "muted" }, "as runs would fill it in"), element("span", { style: "flex:1" }),
        element("button", { class: "again", title: "Other picks", onclick: () => background(previewPicks(name, folder)) }, "🎲 Again"),
        element("button", { class: "close-picks", title: "Close", onclick: () => { picks.hidden = true; } }, "✕")),
      ...result.picks.map((text) => element("div", { class: "pick" }, element("span", { class: "text" }, text || "(nothing)"),
        element("button", { class: "add", title: "Put this text where the cursor was in the prompts", onclick: () => say(`Added it to ${insertIntoNode(node, text)}.`) }, "+ Add"))));
  }
  // The search finds names, and lines too: the wildcards with a line that has the text (from the server, a moment after typing).
  let lineMatches = new Map(), lineQuery = "", searchTimer = null;
  function searchLines() {
    clearTimeout(searchTimer);
    const query = search.value.trim().toLowerCase();
    if (query.length < 2) { lineMatches = new Map(); lineQuery = ""; return; }
    searchTimer = setTimeout(async () => {
      try {
        const response = await api.fetchApi(`/diceforge/wildcards/search?q=${encodeURIComponent(query)}`);
        if (!response.ok || search.value.trim().toLowerCase() !== query) return;
        lineMatches = new Map((await response.json()).found.map((found) => [found.name, found.line]));
        lineQuery = query;
        draw();
      } catch { /* No answer: names only. */ }
    }, 250);
  }
  function draw() {
    const { files } = listCache ?? { files: [] };
    const query = search.value.trim().toLowerCase();
    const byLine = (file) => lineQuery === query && lineMatches.has(file.name);
    const brokenCount = files.filter((file) => file.broken).length;
    if (!brokenCount) onlyBroken = false;
    brokenButton.hidden = !brokenCount;
    brokenButton.textContent = `⚠ Broken (${brokenCount})`;
    brokenButton.classList.toggle("on", onlyBroken);
    const shown = files.filter((file) => (!query || file.name.toLowerCase().includes(query) || byLine(file)) && (!onlyFavorites || file.favorite) && (!onlyBroken || file.broken));
    const allOpen = query || onlyFavorites || onlyBroken; // A search or the filters show their matches in open folders.
    const root = { folders: new Map(), files: [] };
    for (const file of shown) {
      let level = root;
      const parts = file.name.split("/");
      parts.slice(0, -1).forEach((part, index) => {
        if (!level.folders.has(part)) level.folders.set(part, { path: parts.slice(0, index + 1).join("/"), folders: new Map(), files: [] });
        level = level.folders.get(part);
      });
      level.files.push(file);
    }
    const drawLevel = (level) => [
      ...[...level.folders.entries()].map(([part, folder]) => {
        const row = element("div", { class: "row" + (cardsMode && folder.path === cardFolder ? " sel" : "") },
          element("span", { class: "name", title: cardsMode ? "Show its cards (and open or close the folder)" : "Open or close the folder",
            onclick: () => { if (cardsMode) cardFolder = folder.path; toggle(folder.path, cardsMode ? true : undefined); } }, `📁 ${part}`), element("span", { class: "muted" }, "all files"),
          element("button", { class: "add", title: `Insert __${folder.path}/*__`, onclick: () => add(`${folder.path}/*`) }, "+ Add"),
          menuButton(() => folderItems(folder.path), "More: preview, new file, export, convert (or right-click the row)"));
        withMenu(row, () => folderItems(folder.path));
        dropTarget(row, "wildcards", (name) => background(moveFile(name, folder.path))); // A file dropped on a folder moves into it.
        return element("div", { class: "folder" + (allOpen || opened.has(folder.path) ? " open" : ""), "data-path": folder.path }, row, element("div", { class: "kids" }, ...drawLevel(folder)));
      }),
      ...level.files.map((file) => {
        const row = element("div", { class: "row" + (file.name === selected ? " sel" : ""), "data-name": file.name, title: file.error || file.preview.join("\n") },
          element("span", { class: "name", onclick: () => open(file.name) }, file.name.split("/").pop()),
          ...(query && !file.name.toLowerCase().includes(query) && byLine(file) ? [element("span", { class: "found", title: lineMatches.get(file.name) }, `“${lineMatches.get(file.name)}”`)] : []),
          ...(file.broken ? [element("span", { class: "broken", title: `Uses wildcards that don't exist: ${file.broken.map((name) => `__${name}__`).join(", ")}` }, "⚠")] : []),
          element("span", { class: "muted", title: file.error || (file.yaml ? `From ${file.yaml}` : "") },
            file.error ? "⚠ can't be read" : `${file.yaml ? "yaml · " : ""}${file.lines} ${file.lines === 1 ? "line" : "lines"}`),
          element("button", { class: "fav" + (file.favorite ? " on" : ""), title: file.favorite ? "A favorite: click to remove the star" : "Add to favorites",
            onclick: () => background(setFavorite(file.name, !file.favorite)) }, file.favorite ? "★" : "☆"),
          element("button", { class: "add", title: `Insert __${file.name}__`, onclick: () => add(file.name) }, "+ Add"),
          menuButton(() => fileItems(file), "More: open, preview, rename, move, convert, clean up, delete (or right-click the row)"));
        withMenu(row, () => fileItems(file));
        if (!file.yaml) dragSource(row, "wildcards", file.name); // A yaml wildcard moves with its yaml file only.
        return row;
      }),
    ];
    modeButton.textContent = cardsMode ? "📄 Lines" : "🃏 Cards";
    modeButton.classList.toggle("on", cardsMode);
    dialog.classList.toggle("cards-mode", cardsMode);
    editPane.hidden = cardsMode;
    cards.hidden = !cardsMode;
    if (cardsMode) drawCards(shown);
    const items = drawLevel(root);
    tree.replaceChildren(...(items.length ? items : [element("div", { class: "muted" }, files.length ? (onlyFavorites && !query ? "No favorites yet: ☆ next to a file adds it." : "No wildcard matches the search.") : "No wildcard files yet: create one with + New file (they go to ComfyUI/models/wildcards).")]));
  }
  dropTarget(tree, "wildcards", (name) => background(moveFile(name, ""))); // Dropped on the tree, not on a folder: to the top folder.
  search.addEventListener("input", () => { draw(); searchLines(); });
  dialog.addEventListener("dragover", (event) => {
    if (!event.dataTransfer?.types?.includes("Files") || event.target.closest?.(".card")) return; // A picture on a card is the card's.
    event.preventDefault();
    dialog.classList.add("drop-zip");
  });
  dialog.addEventListener("dragleave", (event) => { if (event.target === dialog) dialog.classList.remove("drop-zip"); });
  dialog.addEventListener("drop", (event) => {
    dialog.classList.remove("drop-zip");
    const file = event.dataTransfer?.files?.[0];
    if (!file || event.target.closest?.(".card")) return;
    event.preventDefault();
    if (file.name.toLowerCase().endsWith(".zip")) background(importZip(file));
    else say("Drop a .zip of wildcards here (or a picture on a yaml card).");
  });
  back.append(dialog);
  const heading = element("h2", {}, "Wildcards");
  const stopSize = keepSize(dialog, "wildcards", heading);
  dialog.append(heading,
    element("div", { class: "top" }, search, modeButton, favoritesButton, brokenButton, expandAll, collapseAll, importButton, exportButton, replaceButton, create, element("button", { onclick: close }, "Close")),
    element("div", { class: "main" }, tree, editPane, cards), picks, replacePanel, status);
  editPane.append(title, code, element("div", { class: "top" }, element("span", { style: "flex:1" }), convertButton, remove, move, rename, save));
  const last = recall("wildcards");
  search.value = typeof last.search === "string" ? last.search : "";
  onlyFavorites = last.favorites === true;
  favoritesButton.classList.toggle("on", onlyFavorites);
  if (typeof last.cardFolder === "string") cardFolder = last.cardFolder;
  document.body.append(back);
  await wildcardList(true);
  draw();
  searchLines();
  search.focus();
  search.setSelectionRange(search.value.length, search.value.length);
  if (typeof last.selected === "string" && listCache?.files?.some((file) => file.name === last.selected)) {
    await open(last.selected);
    if (typeof last.draft === "string" && !editor.readOnly && editor.value === last.saved) { // Changed on disk since: the file as it is now.
      editor.value = last.draft;
      showDirty();
      numberLines();
      say("Your unsaved changes from last time are back: Save keeps them.");
    }
    const caret = Math.min(Number(last.caret) || 0, editor.value.length);
    editor.setSelectionRange(caret, caret);
    markCurrentLine();
    scrollBack(editor, last.editor);
  }
  scrollBack(tree, last.tree);
  const grid = cards.querySelector(".grid");
  if (grid) scrollBack(grid, last.cards);
}

app.registerExtension({
  name: "DiceForge.Wildcards",
  getNodeMenuItems(node) {
    // The syntax guide first: this extension registers before the other prompt tools (they all import this module), so its items come first.
    return isPromptNode(node) ? [
      { content: "📖 Syntax guide", callback: () => import("./syntax_guide.js").then((guide) => guide.openSyntaxGuide(node)).catch((error) => console.error("[DiceForge]", error)) },
      { content: "🎲 Wildcard Browser", callback: () => openBrowser(node) },
    ] : [];
  },
});

// A wildcard file without duplicate and empty lines (sorted A→Z by the text, a line's N:: weight left aside, when sort): the comment lines at its
// top stay there. Also how many lines went.
export function cleanLines(text, sort) {
  const lines = text.split("\n").map((line) => line.replace(/\s+$/, ""));
  let start = 0;
  while (start < lines.length && (!lines[start].trim() || lines[start].trim().startsWith("#"))) start++;
  const head = lines.slice(0, start).filter((line) => line.trim()), seen = new Set(), body = [];
  let duplicates = 0, empty = lines.slice(0, start).length - head.length;
  for (const line of lines.slice(start)) {
    if (!line.trim()) empty++;
    else if (seen.has(line.trim())) duplicates++;
    else {
      seen.add(line.trim());
      body.push(line);
    }
  }
  const key = (line) => line.trim().replace(/^\d+(?:\.\d+)?::/, "");
  if (sort) body.sort((a, b) => key(a).localeCompare(key(b), undefined, { sensitivity: "base", numeric: true }));
  return { text: [...head, ...body].join("\n"), duplicates, empty };
}

// For the prompt syntax highlighting (prompt_highlight.js): the prompt fields of a node, and the wildcard names as last listed.
const knownWildcards = () => listCache?.files?.map((file) => file.name) ?? null;
export { insertIntoNode, cursorField, setField, textareaOf, wildcardList, knownWildcards, fieldsOf, isPromptNode, NODE_TYPE as PROMPT_NODE_TYPE, FIELDS as PROMPT_FIELDS };
