import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, background, element } from "./dom.js";
import { dragSource, dropTarget, pickFolder } from "./move_dialog.js";

// Wildcards in CLIP Dual Text Encode: autocomplete after "__" in the prompt fields, and the Wildcard Browser (node menu) with a folder tree,
// "+ Add" buttons that insert __name__ (or __folder/*__) where the cursor was, and an editor for the files.
const NODE_TYPE = "CLIPTextEncodePositiveNegative";
const FIELDS = ["positive", "negative"];

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
// Inserts at the cursor last in the node's prompt fields (or at the end of the positive prompt), or at the end of the field asked for (field) when
// the cursor wasn't in it.
function insertIntoNode(node, token, field) {
  const last = lastCursor.get(node);
  const cursor = (field && last?.name !== field ? { name: field } : last) ?? { name: "positive" };
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
.dfwc .folder>.row .name{font-weight:600}.dfwc .folder>.row .name::before{content:"▸ ";color:#999}.dfwc .folder.open>.row .name::before{content:"▾ "}
.dfwc .kids{margin-left:16px}.dfwc button.fav{border:none;background:none;padding:0 4px;font-size:15px;color:#888}.dfwc button.fav.on{color:#ffd24a}
.dfwc button.only-favorites.on{border-color:#b8962e;color:#ffd24a}.dfwc .row.drop,.dfwc .tree.drop{background:#35584a;outline:1px dashed #8fd0a8}.dfwc .folder:not(.open)>.kids{display:none}.dfwc .muted{color:#999;font-size:12px}
.dfwc button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit}.dfwc button:hover{background:#2c2c2c}
.dfwc button:disabled{opacity:.5;cursor:default}.dfwc button.delete:not(:disabled){border-color:#8a4a4a;color:#f0b0b0}.dfwc textarea[readonly]{color:#aaa}.dfwc button.add{padding:1px 8px;font-size:12px;border-color:#4a7a4a;color:#bfe8bf}.dfwc .status{color:#9c9;min-height:18px;font-size:13px}
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
async function updatePopup(textarea) {
  const request = ++popupRequest;
  if (!fieldOf(textarea)) return closePopup();
  const before = textarea.value.slice(0, textarea.selectionStart);
  const found = sources.map((source) => source(before)).find(Boolean);
  if (!found) return closePopup();
  const items = await found.items;
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
  const point = caretPoint(textarea);
  Object.assign(popup.element.style, { left: `${Math.min(point.x, innerWidth - 260)}px`, top: `${Math.min(point.y, innerHeight - 120)}px` });
  renderPopup();
}
function accept(index) {
  const item = popup.items[index];
  const textarea = popup.textarea;
  const skip = popup.skip; // Read before closePopup.
  if (!item || !textarea) return closePopup();
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
  event.stopPropagation();
}, true);
document.addEventListener("focusout", (event) => { if (event.target === popup.textarea) setTimeout(closePopup, 150); rememberCursor(event); }, true);
for (const type of ["keyup", "mouseup", "focusin"]) document.addEventListener(type, rememberCursor, true);

// Folders open in the Wildcard Browser, kept between openings (and reloads) in this browser. Folders start closed; a search opens them all.
const OPEN_KEY = "diceforge.wildcards.open";
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
  const search = element("input", { placeholder: "Search wildcards…" });
  const tree = element("div", { class: "tree" });
  const title = element("div", { class: "muted" }, "Select a file to see and edit its lines, one option per line (# starts a comment).");
  const editor = element("textarea", { placeholder: "One option per line" });
  const status = element("div", { class: "status" });
  const save = element("button", { class: "save" }, "Save");
  const rename = element("button", { class: "rename", disabled: true }, "Rename");
  const move = element("button", { class: "move", disabled: true, title: "Move the file to another folder (or drag it onto a folder in the tree)" }, "⇄ Move");
  const remove = element("button", { class: "delete", disabled: true }, "Delete");
  let selected = null, saved = "";
  const showDirty = () => { save.textContent = selected && !editor.readOnly && editor.value !== saved ? "Save •" : "Save"; };
  editor.addEventListener("input", showDirty);
  editor.addEventListener("keydown", (event) => {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") { event.preventDefault(); event.stopPropagation(); save.click(); }
  });
  const back = element("div", { class: "dfwc-back" });
  const close = () => { back.remove(); document.removeEventListener("keydown", onKey, true); };
  const onKey = (event) => { if (event.key === "Escape" && !document.querySelector(".dfmv-back")) { event.stopPropagation(); close(); } }; // The folder picker closes first.
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  const say = (text) => { status.textContent = text; };
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
    editor.readOnly = !!file.readonly; // A yaml wildcard is one key of a yaml file: edited in that file.
    save.disabled = rename.disabled = move.disabled = remove.disabled = !!file.readonly;
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
    } else draw();
    say(`${moved ? "Moved" : "Renamed"} ${result.renamed} to ${result.to}. Prompts that use __${result.renamed}__ need the new name.`);
  }
  rename.addEventListener("click", async () => {
    if (!selected) return;
    const to = prompt("New name (folders with /, for example hair/color):", selected)?.trim();
    if (to && to !== selected) await renameTo(selected, to, false);
  });
  // Move: the same file name in another folder ("" for the top folder), picked in the folder picker or by dropping the file on a folder.
  async function moveFile(name, to) {
    const parts = name.split("/"), from = parts.slice(0, -1).join("/");
    const destination = to ?? await pickFolder({ title: `Move ${parts.at(-1)} to…`, folders: folderNames(listCache?.files ?? []), current: from });
    if (destination == null || destination === from) return;
    await renameTo(name, `${destination ? `${destination}/` : ""}${parts.at(-1)}`, true);
  }
  move.addEventListener("click", () => { if (selected) background(moveFile(selected)); });
  remove.addEventListener("click", async () => {
    if (!selected || !confirm(`Delete the wildcard file ${selected}.txt? This can't be undone.`)) return;
    const response = await api.fetchApi(`/diceforge/wildcards/file?name=${encodeURIComponent(selected)}`, { method: "DELETE" });
    if (!response.ok) return say(await response.text());
    const name = selected;
    selected = null;
    editor.value = saved = "";
    editor.readOnly = false;
    rename.disabled = move.disabled = remove.disabled = true;
    showDirty();
    title.replaceChildren("Select a file to see and edit its lines, one option per line (# starts a comment).");
    await wildcardList(true);
    draw();
    say(`Deleted ${name}.txt.`);
  });
  const create = element("button", { onclick: async () => {
    const name = prompt("New wildcard file name (folders with /, for example hair/color):", search.value.trim());
    if (!name) return;
    const response = await api.fetchApi("/diceforge/wildcards/file", { method: "POST", body: JSON.stringify({ name, text: "", create: true }) });
    if (!response.ok) return say(await response.text());
    await wildcardList(true);
    await open((await response.json()).saved);
  } }, "+ New file");
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
  let onlyFavorites = false;
  const favoritesButton = element("button", { class: "only-favorites", title: "Show only your favorites (☆ on a file)", onclick: () => {
    onlyFavorites = !onlyFavorites;
    favoritesButton.classList.toggle("on", onlyFavorites);
    draw();
  } }, "★ Favorites");
  async function setFavorite(name, favorite) {
    const response = await api.fetchApi("/diceforge/wildcards/favorite", { method: "POST", body: JSON.stringify({ name, favorite }) });
    if (!response.ok) return say(await response.text());
    await wildcardList(true); // The autocomplete gets the star too.
    say(favorite ? `__${name}__ is a favorite.` : `__${name}__ is no longer a favorite.`);
    draw();
  }
  function draw() {
    const { files } = listCache ?? { files: [] };
    const query = search.value.trim().toLowerCase();
    const shown = files.filter((file) => (!query || file.name.toLowerCase().includes(query)) && (!onlyFavorites || file.favorite));
    const allOpen = query || onlyFavorites; // A search or the favorites show their matches in open folders.
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
        const row = element("div", { class: "row" }, element("span", { class: "name", title: "Open or close the folder", onclick: () => toggle(folder.path) }, `📁 ${part}`), element("span", { class: "muted" }, "all files"),
          element("button", { class: "add", title: `Insert __${folder.path}/*__`, onclick: () => add(`${folder.path}/*`) }, "+ Add"));
        dropTarget(row, "wildcards", (name) => background(moveFile(name, folder.path))); // A file dropped on a folder moves into it.
        return element("div", { class: "folder" + (allOpen || opened.has(folder.path) ? " open" : ""), "data-path": folder.path }, row, element("div", { class: "kids" }, ...drawLevel(folder)));
      }),
      ...level.files.map((file) => {
        const row = element("div", { class: "row" + (file.name === selected ? " sel" : ""), "data-name": file.name, title: file.error || file.preview.join("\n") },
          element("span", { class: "name", onclick: () => open(file.name) }, file.name.split("/").pop()),
          element("span", { class: "muted", title: file.error || (file.yaml ? `From ${file.yaml}` : "") },
            file.error ? "⚠ can't be read" : `${file.yaml ? "yaml · " : ""}${file.lines} ${file.lines === 1 ? "line" : "lines"}`),
          element("button", { class: "fav" + (file.favorite ? " on" : ""), title: file.favorite ? "A favorite: click to remove the star" : "Add to favorites",
            onclick: () => background(setFavorite(file.name, !file.favorite)) }, file.favorite ? "★" : "☆"),
          element("button", { class: "add", title: `Insert __${file.name}__`, onclick: () => add(file.name) }, "+ Add"));
        if (!file.yaml) dragSource(row, "wildcards", file.name); // A yaml wildcard moves with its yaml file only.
        return row;
      }),
    ];
    const items = drawLevel(root);
    tree.replaceChildren(...(items.length ? items : [element("div", { class: "muted" }, files.length ? (onlyFavorites && !query ? "No favorites yet: ☆ next to a file adds it." : "No wildcard matches the search.") : "No wildcard files yet: create one with + New file (they go to ComfyUI/models/wildcards).")]));
  }
  dropTarget(tree, "wildcards", (name) => background(moveFile(name, ""))); // Dropped on the tree, not on a folder: to the top folder.
  search.addEventListener("input", draw);
  back.append(element("div", { class: "dfwc" },
    element("h2", {}, "Wildcards"),
    element("div", { class: "top" }, search, favoritesButton, expandAll, collapseAll, create, element("button", { onclick: close }, "Close")),
    element("div", { class: "main" }, tree, element("div", { class: "edit" }, title, editor, element("div", { class: "top" }, status, element("span", { style: "flex:1" }), remove, move, rename, save)))));
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

// For the prompt syntax highlighting (prompt_highlight.js): the prompt fields of a node, and the wildcard names as last listed.
const knownWildcards = () => listCache?.files?.map((file) => file.name) ?? null;
export { insertIntoNode, setField, textareaOf, wildcardList, knownWildcards, NODE_TYPE as PROMPT_NODE_TYPE, FIELDS as PROMPT_FIELDS };
