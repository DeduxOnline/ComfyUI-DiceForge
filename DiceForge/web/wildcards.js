import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, askConfirm, askText, background, element } from "./dom.js";
import { toast } from "./comfy.js";
import { addThemeStyle } from "./theme.js";

// Wildcards in CLIP Dual Text Encode: autocomplete after "__" in the prompt fields, the node menu's Wildcard Browser (wildcard_browser.js) and
// ✂ Selection → new wildcard, and what the other prompt tools share: the prompt fields, inserting at the cursor, the wildcard list.
// The Wildcard Browser's code, loaded when it is first opened (it imports this module).
const openBrowser = (node) => import("./wildcard_browser.js").then((browser) => browser.openBrowser(node));
const NODE_TYPE = "DiceForgeCLIPDualTextEncode";
const FIELDS = ["positive", "negative"];
// The nodes whose text fields get the prompt tools (autocomplete, highlighting, the browsers' + Add, the syntax guide), and their fields.
const PROMPT_NODES = { [NODE_TYPE]: FIELDS, DiceForgeWildcardsToText: ["text"], DiceForgeWildcardNote: ["text"] };
const fieldsOf = (node) => PROMPT_NODES[node?.comfyClass] ?? null;
const isPromptNode = (node) => !!fieldsOf(node);

// The wildcard list, fetched once and shared: keystrokes while it loads wait for the same request instead of each sending one (their answers could
// come back in any order). listCache is the last list that arrived, for drawing the browser; the listeners hear of each new list (Wildcard Note's
// file list follows the files made, renamed and deleted elsewhere).
let listCache = null, listRequest = null;
const listListeners = new Set();
export const onWildcardList = (listener) => { listListeners.add(listener); return () => listListeners.delete(listener); }; // Gives what stops it.
function wildcardList(refresh = false) {
  if (!listRequest || refresh) {
    const request = api.fetchApi("/diceforge/wildcards")
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error(`${response.status}`))))
      .then((list) => { // An older request finishing late doesn't win.
        if (listRequest === request) {
          listCache = list;
          listListeners.forEach((listener) => listener(list));
        }
        return list;
      },
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
.dfwc-pop{position:fixed;z-index:10001;min-width:220px;max-width:420px;max-height:280px;overflow:auto;padding:3px}
.dfwc-pop div{padding:4px 8px;border-radius:4px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dfwc-pop div.on{background:var(--df-pop-on)}
.dfwc .picks{border:1px solid #4a6a9a;background:#2a3444;border-radius:6px;padding:6px 8px;margin-top:8px;max-height:32%;overflow:auto}
.dfwc .picks-head{display:flex;gap:8px;align-items:center;margin-bottom:4px}.dfwc .picks .pick{display:flex;gap:8px;align-items:center;padding:3px 0;border-top:1px solid #3a4a64}
.dfwc .picks .pick .text{flex:1;min-width:0;white-space:pre-wrap;word-break:break-word}.dfwc .picks button{padding:1px 8px;font-size:12px}
.dfwc .row .broken{color:#ff8a8a;cursor:help}.dfwc .row.cursor{outline:1px solid #6a9ad8;outline-offset:-1px}.dfwc .top{flex-wrap:wrap}
.dfwc .replace{border:1px solid #6a5a9a;background:#2e2a44;border-radius:6px;padding:6px 8px;margin-top:8px;max-height:36%;overflow:auto}
.dfwc .replace-head{display:flex;gap:6px;align-items:center;flex-wrap:wrap}.dfwc .replace-head input{flex:1;min-width:140px}
.dfwc .replace .change{display:flex;gap:8px;padding:3px 0;border-top:1px solid #443c64;font-size:12px}.dfwc .replace .change b{min-width:120px}
.dfwc .replace .change .after{color:#9c9}.dfwc .replace .change .before{color:#c99;text-decoration:line-through}.dfwc .status button.more-action{margin-left:6px;padding:0 8px;font-size:12px}
.dfwc .row button.more{border:none;background:none;color:#999;padding:0 4px;font-size:15px}.dfwc .row button.more:hover{color:#fff}.dfwc-pop .n{color:var(--descrip-text,#999);float:right;margin-left:12px}.dfwc-pop .browse{color:var(--df-link);border-top:1px solid var(--border-color,#444);margin-top:2px}
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
.dfwc .card .actions{display:flex;flex-wrap:wrap;gap:4px;align-items:center;margin-top:auto}.dfwc .card .actions button{white-space:nowrap}.dfwc .card .actions button.add{margin-left:auto}.dfwc .card .title-row{display:flex;align-items:flex-start;gap:4px}.dfwc .card .title-row .title{flex:1}.dfwc .card .title-row button.more{padding:0 6px;font-size:12px}
.dfwc button.mode.on,.dfwc button.line-cards.on{border-color:#6a9ad8;background:#2f3f55}.dfwc .card.line-card .title{font-weight:500}
.dfwc .row{display:flex;align-items:center;gap:6px;padding:3px 6px;border-radius:4px}.dfwc .row:hover{background:#2c2c2c}
.dfwc .row .name{flex:1;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dfwc .row.sel{background:#2f3f55}
.dfwc .folder>.row .name{font-weight:600}.dfwc .folder>.row .name::before{content:"▸ ";color:#999}.dfwc .folder.open>.row .name::before{content:"▾ "}
.dfwc .kids{margin-left:16px}.dfwc button.fav{border:none;background:none;padding:0 4px;font-size:15px;color:#888}.dfwc button.fav.on{color:#ffd24a}
.dfwc button.only-favorites.on{border-color:#b8962e;color:#ffd24a}.dfwc .row.drop,.dfwc .tree.drop{background:#35584a;outline:1px dashed #8fd0a8}.dfwc .folder:not(.open)>.kids{display:none}.dfwc .muted{color:#999;font-size:12px}
.dfwc button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit}.dfwc button:hover{background:#2c2c2c}
.dfwc button.convert{padding:1px 7px;font-size:12px;border-color:#5a6f9a;color:#bcd0f5}.dfwc .row button.export{padding:1px 7px;font-size:12px}.dfwc .edit button.convert{padding:5px 12px;font-size:inherit}
.dfwc .card .actions button.picture,.dfwc .card .actions button.no-picture,.dfwc .card .actions button.edit-card{padding:1px 6px;font-size:12px}
.dfwc .card .card-edit{display:flex;flex-direction:column;gap:6px;padding:6px 8px;flex:1}.dfwc .card .card-edit textarea{min-height:120px;resize:vertical;font:12px/18px ui-monospace,monospace;white-space:pre}
.dfwc .card .card-edit .buttons{display:flex;gap:6px;justify-content:flex-end}.dfwc .card .card-edit button{padding:2px 10px;font-size:12px}.dfwc .card.drop{outline:2px dashed #8fd0a8}
.dfwc button:disabled{opacity:.5;cursor:default}.dfwc button.delete:not(:disabled){border-color:#8a4a4a;color:#f0b0b0}.dfwc button.add{padding:1px 8px;font-size:12px;border-color:#4a7a4a;color:#bfe8bf}.dfwc .status{color:#9c9;min-height:18px;font-size:13px}.dfwc .status button.undo{margin-left:10px;padding:0 8px;font-size:12px}
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
    addThemeStyle();
    popup.element = element("div", { class: "dfwc-pop df-pop" });
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

app.registerExtension({
  name: "DiceForge.Wildcards",
  getNodeMenuItems(node) {
    // The syntax guide first: this extension registers before the other prompt tools (they all import this module), so its items come first.
    return isPromptNode(node) ? [
      { content: "📖 Syntax guide", callback: () => import("./syntax_guide.js").then((guide) => guide.openSyntaxGuide(node)).catch((error) => console.error("[DiceForge]", error)) },
      { content: "🎲 Wildcard Browser", callback: () => openBrowser(node) },
      { content: "✂ Selection → new wildcard…", callback: () => background(selectionToWildcard(node)) },
    ] : [];
  },
});

// A wildcard file without duplicate and empty lines (sorted A→Z by the text, a line's N:: weight left aside, when sort): the comment lines at its
// top stay there. Also how many lines went.
export function cleanLines(text, sort) {
  const lines = text.split("\n").map((line) => line.trimEnd());
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

// Text helpers of the Wildcard Browser and ✂ Selection → new wildcard, without regular expressions that could backtrack on a long text
// (tests/test_frontend_text.py checks them against the expressions they replace).
// A text as one line: its lines trimmed and joined with a space, empty ones left out.
export function oneLine(text) {
  return text.split("\n").map((line) => line.trim()).filter(Boolean).join(" ");
}
// A text without the line breaks at its end (the spaces of its last line stay).
export function withoutTrailingNewlines(text) {
  let end = text.length;
  while (end > 0 && text[end - 1] === "\n") end--;
  return text.slice(0, end);
}
// A line's option in a yaml file: the text after "key:" or "- ", without its quotes (a key of keys, or a [list] on one line, has none).
export function yamlOption(line) {
  const text = line.trim(), colon = text.indexOf(":");
  let value = "";
  if (/^-\s/.test(text)) value = text.slice(1).trim();
  else if (!text.startsWith("#") && colon > 0 && /\s/.test(text[colon + 1] ?? "")) value = text.slice(colon + 1).trim();
  if (/^[[{]/.test(value)) return "";
  return /^(["']).*\1$/.test(value) ? value.slice(1, -1) : value;
}
// The name ✂ Selection → new wildcard proposes: the first three words of the selection, joined with _.
export function suggestedName(line) {
  return line.toLowerCase().split(/[^\p{L}\p{N}]+/u).filter(Boolean).slice(0, 3).join("_") || "new";
}
// ✂ Selection → new wildcard: the part of a prompt selected (the last selection in the node's prompt fields) becomes a wildcard file's first
// line, and __name__ takes its place in the prompt: a prompt split into wildcards, one choice at a time. A name already taken: the selection
// is added to that file as one more line (asked first).
async function selectionToWildcard(node) {
  const cursor = lastCursor.get(node);
  const text = String(node.widgets?.find((widget) => widget.name === cursor?.name)?.value ?? "");
  const start = cursor?.start ?? 0, end = cursor?.end ?? 0, picked = text.slice(start, end);
  if (!cursor || !picked.trim()) return toast("warn", "Wildcards", "Select a part of a prompt first: it becomes the new wildcard's first line, and __name__ takes its place.");
  const line = oneLine(picked);
  const suggested = suggestedName(line);
  const quoted = line.length > 60 ? `${line.slice(0, 60)}…` : line;
  const name = (await askText(`A wildcard from “${quoted}”: its name (folders with /, for example outfit/dress):`, suggested))?.trim();
  if (!name) return;
  const save = (body) => api.fetchApi("/diceforge/wildcards/file", { method: "POST", body: JSON.stringify(body) });
  let response = await save({ name, text: line, create: true }), what = "Made";
  if (response.status === 409) { // Taken: one more line of it?
    if (!(await askConfirm(`__${name}__ already exists. Add “${line}” to it as a new line?`))) return;
    const file = await api.fetchApi(`/diceforge/wildcards/file?name=${encodeURIComponent(name)}`);
    if (!file.ok) return toast("error", "Wildcards", await file.text());
    const current = await file.json();
    const known = current.text.split("\n").some((item) => item.trim() === line);
    response = known ? new Response(JSON.stringify({ saved: name })) : await save({ name, text: current.text.trim() ? `${current.text}\n${line}` : line });
    what = known ? "Used" : "Added a line to";
  }
  if (!response.ok) return toast("error", "Wildcards", await response.text());
  const token = `__${(await response.json()).saved}__`;
  const lead = picked.slice(0, picked.length - picked.trimStart().length), trail = picked.slice(picked.trimEnd().length); // The selection's spaces stay around the wildcard.
  const caret = start + lead.length + token.length;
  setField(node, cursor.name, text.slice(0, start) + lead + token + trail + text.slice(end), caret);
  lastCursor.set(node, { name: cursor.name, start: caret, end: caret });
  await wildcardList(true);
  toast("success", "Wildcards", `${what} ${token}: it now stands for “${line}” in the ${cursor.name} prompt.`);
}

// For the prompt syntax highlighting (prompt_highlight.js): the prompt fields of a node, and the wildcard names as last listed.
const knownWildcards = () => listCache?.files?.map((file) => file.name) ?? null;
export { insertIntoNode, cursorField, setField, textareaOf, wildcardList, knownWildcards, listCache, folderNames, addStyle, fieldsOf, isPromptNode,
  NODE_TYPE as PROMPT_NODE_TYPE, FIELDS as PROMPT_FIELDS };
