import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

// Wildcards in CLIP Dual Text Encode: autocomplete after "__" in the prompt fields, and the Wildcard Browser (node menu) with a folder tree,
// "+ Add" buttons that insert __name__ (or __folder/*__) where the cursor was, and an editor for the files.
const NODE_TYPE = "CLIPTextEncodePositiveNegative";
const FIELDS = ["positive", "negative"];

let listCache = null;
async function wildcardList(refresh = false) {
  if (!listCache || refresh) {
    const response = await api.fetchApi("/diceforge/wildcards");
    listCache = response.ok ? await response.json() : { files: [], folders: [] };
  }
  return listCache;
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
    if (node?.comfyClass !== NODE_TYPE) return null;
    const labelText = textarea.closest('[data-testid="node-widget"]')?.innerText?.trim();
    const byLabel = node.widgets?.find((widget) => FIELDS.includes(widget.name) && labelText && labelText.startsWith(widget.label || widget.name))?.name;
    const name = byLabel ?? FIELDS[textareasOf(nodeElement.dataset.nodeId).indexOf(textarea)];
    return name ? { node, name } : null;
  }
  for (const node of app.graph?.nodes ?? []) {
    if (node.comfyClass !== NODE_TYPE) continue;
    const widget = node.widgets?.find((widget) => FIELDS.includes(widget.name) && (widget.inputEl === textarea || widget.element?.contains?.(textarea)));
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
function insertIntoNode(node, token) {
  const cursor = lastCursor.get(node) ?? { name: "positive" };
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
.dfwc-pop div.on{background:#3a5a8a;color:#fff}.dfwc-pop .n{color:#999;float:right;margin-left:12px}.dfwc-pop .browse{color:#9cc8ff;border-top:1px solid #444;margin-top:2px}
.dfwc-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dfwc{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(1100px,95vw);height:min(760px,90vh);display:flex;flex-direction:column;padding:16px 18px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dfwc h2{margin:0 0 10px;font-size:20px;color:#fff}.dfwc .top{display:flex;gap:8px;margin-bottom:10px}
.dfwc input,.dfwc textarea{background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:6px 8px;font:inherit;box-sizing:border-box}
.dfwc .top input{flex:1}.dfwc .main{display:flex;gap:12px;flex:1;min-height:0}
.dfwc .tree{width:45%;overflow:auto;border:1px solid #4a4a4a;border-radius:6px;padding:6px}
.dfwc .edit{flex:1;display:flex;flex-direction:column;gap:8px;min-width:0}.dfwc .edit textarea{flex:1;resize:none;font:13px ui-monospace,monospace}
.dfwc .row{display:flex;align-items:center;gap:6px;padding:3px 6px;border-radius:4px}.dfwc .row:hover{background:#2c2c2c}
.dfwc .row .name{flex:1;cursor:pointer;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dfwc .row.sel{background:#2f3f55}
.dfwc .folder>.row .name{font-weight:600}.dfwc .kids{margin-left:16px}.dfwc .muted{color:#999;font-size:12px}
.dfwc button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit}.dfwc button:hover{background:#2c2c2c}
.dfwc button:disabled{opacity:.5;cursor:default}.dfwc textarea[readonly]{color:#aaa}.dfwc button.add{padding:1px 8px;font-size:12px;border-color:#4a7a4a;color:#bfe8bf}.dfwc .status{color:#9c9;min-height:18px;font-size:13px}
`;
function addStyle() {
  if (document.getElementById("dfwc-style")) return;
  const style = document.createElement("style");
  style.id = "dfwc-style";
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

// Autocomplete: after an opening "__" (an odd number of "__" before the cursor), the wildcards and folders (folder/*) that contain what is typed.
const popup = { element: null, textarea: null, items: [], index: 0, start: 0 };
function caretPoint(textarea) {
  const style = getComputedStyle(textarea);
  const mirror = document.createElement("div");
  for (const property of ["fontFamily", "fontSize", "fontWeight", "lineHeight", "letterSpacing", "padding", "border", "boxSizing", "whiteSpace", "wordWrap", "tabSize"]) mirror.style[property] = style[property];
  Object.assign(mirror.style, { position: "absolute", visibility: "hidden", whiteSpace: "pre-wrap", wordWrap: "break-word", width: `${textarea.clientWidth}px` });
  mirror.textContent = textarea.value.slice(0, textarea.selectionStart);
  const marker = document.createElement("span");
  marker.textContent = "​";
  mirror.append(marker);
  document.body.append(mirror);
  const rect = textarea.getBoundingClientRect();
  const point = { x: rect.left + marker.offsetLeft - textarea.scrollLeft, y: rect.top + marker.offsetTop - textarea.scrollTop + marker.offsetHeight + 2 };
  mirror.remove();
  return point;
}
function closePopup() {
  popup.element?.remove();
  popup.element = null;
  popup.textarea = null;
}
function renderPopup() {
  popup.element.replaceChildren(...popup.items.map((item, index) => {
    const row = element("div", { class: (index === popup.index ? "on " : "") + (item.browse ? "browse" : "") },
      item.browse ? "📂 Browse wildcards…" : `__${item.token}__`, ...(item.lines != null ? [element("span", { class: "n" }, `${item.lines}`)] : []));
    row.addEventListener("mousedown", (event) => { event.preventDefault(); accept(index); });
    return row;
  }));
  popup.element.children[popup.index]?.scrollIntoView({ block: "nearest" });
}
async function updatePopup(textarea) {
  const before = textarea.value.slice(0, textarea.selectionStart);
  const open = before.split("__").length % 2 === 0; // An odd number of "__": inside a wildcard being typed.
  const match = /__([\w\-./*? ]*)$/.exec(before);
  if (!open || !match || !fieldOf(textarea)) return closePopup();
  const typed = match[1].toLowerCase();
  const { files } = await wildcardList();
  const entries = [...files.map((file) => ({ token: file.name, lines: file.lines })), ...folderNames(files).map((folder) => ({ token: `${folder}/*`, lines: null }))];
  const found = entries.filter((entry) => entry.token.toLowerCase().includes(typed))
    .sort((a, b) => (b.token.toLowerCase().startsWith(typed) - a.token.toLowerCase().startsWith(typed)) || a.token.localeCompare(b.token)).slice(0, 12);
  popup.items = [...found, { browse: true }];
  popup.index = 0;
  popup.start = before.length - match[0].length;
  popup.textarea = textarea;
  if (!popup.element) {
    addStyle();
    popup.element = element("div", { class: "dfwc-pop" });
    document.body.append(popup.element);
  }
  const point = caretPoint(textarea);
  Object.assign(popup.element.style, { left: `${Math.min(point.x, innerWidth - 260)}px`, top: `${Math.min(point.y, innerHeight - 120)}px` });
  renderPopup();
}
function accept(index) {
  const item = popup.items[index];
  const textarea = popup.textarea;
  if (!item || !textarea) return closePopup();
  const field = fieldOf(textarea);
  closePopup();
  if (!field) return;
  if (item.browse) {
    lastCursor.set(field.node, { name: field.name, start: textarea.selectionStart, end: textarea.selectionEnd });
    return openBrowser(field.node);
  }
  const start = popup.start, end = textarea.selectionStart;
  const after = textarea.value.slice(end).startsWith("__") ? 2 : 0; // Typed closing underscores are replaced too.
  const token = `__${item.token}__`;
  setField(field.node, field.name, textarea.value.slice(0, start) + token + textarea.value.slice(end + after), start + token.length);
}
document.addEventListener("input", (event) => { if (event.target?.tagName === "TEXTAREA" && event.isTrusted) updatePopup(event.target); }, true);
document.addEventListener("keydown", (event) => {
  if (!popup.element || event.target !== popup.textarea) return;
  const keys = { ArrowDown: 1, ArrowUp: -1 };
  if (event.key in keys) popup.index = (popup.index + keys[event.key] + popup.items.length) % popup.items.length, renderPopup();
  else if (event.key === "Enter" || event.key === "Tab") accept(popup.index);
  else if (event.key === "Escape") closePopup();
  else return;
  event.preventDefault();
  event.stopPropagation();
}, true);
document.addEventListener("focusout", (event) => { if (event.target === popup.textarea) setTimeout(closePopup, 150); rememberCursor(event); }, true);
for (const type of ["keyup", "mouseup", "focusin"]) document.addEventListener(type, rememberCursor, true);

// Wildcard Browser: folder tree with search, "+ Add" for files (__name__) and folders (__folder/*__), and an editor for the selected file.
async function openBrowser(node) {
  addStyle();
  const search = element("input", { placeholder: "Search wildcards…" });
  const tree = element("div", { class: "tree" });
  const title = element("div", { class: "muted" }, "Select a file to see and edit its lines, one option per line (# starts a comment).");
  const editor = element("textarea", { placeholder: "One option per line" });
  const status = element("div", { class: "status" });
  const save = element("button", {}, "Save");
  let selected = null;
  const back = element("div", { class: "dfwc-back" });
  const close = () => { back.remove(); document.removeEventListener("keydown", onKey, true); };
  const onKey = (event) => { if (event.key === "Escape") { event.stopPropagation(); close(); } };
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  const say = (text) => { status.textContent = text; };
  const add = (token) => { const field = insertIntoNode(node, `__${token}__`); say(`Added __${token}__ to ${field}.`); };
  async function open(name) {
    const response = await api.fetchApi(`/diceforge/wildcards/file?name=${encodeURIComponent(name)}`);
    if (!response.ok) return say(await response.text());
    const file = await response.json();
    selected = name;
    title.replaceChildren(element("b", {}, `__${name}__`), " ", element("span", { class: "muted" }, file.path));
    editor.value = file.text;
    editor.readOnly = !!file.readonly; // A yaml wildcard is one key of a yaml file: edited in that file.
    save.disabled = !!file.readonly;
    say(file.readonly ? "From a yaml file: read-only here, edit the yaml file to change it." : "");
    draw();
  }
  save.addEventListener("click", async () => {
    if (!selected) return say("Select or create a file first.");
    const response = await api.fetchApi("/diceforge/wildcards/file", { method: "POST", body: JSON.stringify({ name: selected, text: editor.value }) });
    say(response.ok ? `Saved ${selected}.txt.` : await response.text());
    await wildcardList(true);
    draw();
  });
  const create = element("button", { onclick: async () => {
    const name = prompt("New wildcard file name (folders with /, for example hair/color):", search.value.trim());
    if (!name) return;
    const response = await api.fetchApi("/diceforge/wildcards/file", { method: "POST", body: JSON.stringify({ name, text: "" }) });
    if (!response.ok) return say(await response.text());
    await wildcardList(true);
    await open((await response.json()).saved);
  } }, "+ New file");
  function draw() {
    const { files } = listCache ?? { files: [] };
    const query = search.value.trim().toLowerCase();
    const shown = files.filter((file) => !query || file.name.toLowerCase().includes(query));
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
      ...[...level.folders.entries()].map(([part, folder]) => element("div", { class: "folder" },
        element("div", { class: "row" }, element("span", { class: "name" }, `📁 ${part}`), element("span", { class: "muted" }, "all files"),
          element("button", { class: "add", title: `Insert __${folder.path}/*__`, onclick: () => add(`${folder.path}/*`) }, "+ Add")),
        element("div", { class: "kids" }, ...drawLevel(folder)))),
      ...level.files.map((file) => element("div", { class: "row" + (file.name === selected ? " sel" : ""), title: file.preview.join("\n") },
        element("span", { class: "name", onclick: () => open(file.name) }, file.name.split("/").pop()),
        element("span", { class: "muted", title: file.yaml ? `From ${file.yaml}` : "" }, `${file.yaml ? "yaml · " : ""}${file.lines} ${file.lines === 1 ? "line" : "lines"}`),
        element("button", { class: "add", title: `Insert __${file.name}__`, onclick: () => add(file.name) }, "+ Add"))),
    ];
    const items = drawLevel(root);
    tree.replaceChildren(...(items.length ? items : [element("div", { class: "muted" }, files.length ? "No wildcard matches the search." : "No wildcard files yet: create one with + New file (they go to ComfyUI/models/wildcards).")]));
  }
  search.addEventListener("input", draw);
  back.append(element("div", { class: "dfwc" },
    element("h2", {}, "Wildcards"),
    element("div", { class: "top" }, search, create, element("button", { onclick: close }, "Close")),
    element("div", { class: "main" }, tree, element("div", { class: "edit" }, title, editor, element("div", { class: "top" }, status, element("span", { style: "flex:1" }), save)))));
  document.body.append(back);
  await wildcardList(true);
  draw();
  search.focus();
}

app.registerExtension({
  name: "DiceForge.Wildcards",
  getNodeMenuItems(node) {
    return node.comfyClass === NODE_TYPE ? [{ content: "🎲 Wildcard Browser", callback: () => openBrowser(node) }] : [];
  },
});
