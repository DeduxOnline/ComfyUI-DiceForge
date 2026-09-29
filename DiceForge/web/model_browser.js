import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { openModelInfo } from "./model_info.js";
import { insertIntoNode } from "./wildcards.js";

// Model browsers (node menu): LoRA and Checkpoint Browser. The model files as cards with a preview, name, base model and trigger words from Civitai
// (looked up by the file's hash, as in Model info), a folder tree, search and filters. What a card's button does depends on the node it was opened
// from: "Use" puts the file in a loader's list, "Use folder" puts a folder in Random LoRA / Random Checkpoint, "+ Triggers" inserts a LoRA's trigger
// words into CLIP Dual Text Encode's prompt.
const CLIP_NODE = "CLIPTextEncodePositiveNegative";
const BROWSERS = [
  { kind: "loras", icon: "🎴", title: "LoRA", one: "LoRA", plural: "LoRAs", widget: /lora/i, random: "DiceForgeRandomLora", randomName: "Random LoRA", triggers: true },
  { kind: "checkpoints", icon: "🗃️", title: "Checkpoint", one: "checkpoint", plural: "checkpoints", widget: /ckpt|checkpoint/i, random: "DiceForgeRandomCheckpoint", randomName: "Random Checkpoint", triggers: false },
];

// What a browser can do for a node: set a model list widget, set a folder widget, or insert trigger words. null when the node has none of them.
function targetOf(node, spec) {
  if (node.comfyClass === CLIP_NODE) return spec.triggers ? { triggers: true } : null;
  const combo = (widget) => Array.isArray(widget.options?.values);
  if (node.comfyClass === spec.random) {
    const folder = node.widgets?.find((widget) => widget.name === "folder" && combo(widget));
    return folder ? { folder } : null;
  }
  const model = node.widgets?.find((widget) => spec.widget.test(widget.name) && combo(widget) && widget.options.values.some((value) => /\.(safetensors|ckpt|pt|pth|bin|gguf|sft)$/i.test(value)));
  return model ? { model } : null;
}
function setWidget(node, widget, value) {
  widget.value = value;
  widget.callback?.(value, app.canvas, node);
  node.setDirtyCanvas?.(true, true);
  app.graph?.setDirtyCanvas?.(true, true);
}

const STYLE = `
.dflb-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dflb{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(1400px,96vw);height:min(900px,92vh);display:flex;flex-direction:column;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dflb h2{margin:0 0 10px;font-size:20px;color:#fff}.dflb .top{display:flex;gap:8px;margin-bottom:10px;align-items:center;flex-wrap:wrap}
.dflb input,.dflb select{background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:6px 8px;font:inherit}.dflb .top input{flex:1;min-width:160px}
.dflb button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit}.dflb button:hover{background:#2c2c2c}
.dflb button:disabled{opacity:.5;cursor:default}.dflb button.go{border-color:#4a7a4a;color:#bfe8bf}
.dflb .main{display:flex;gap:12px;flex:1;min-height:0}.dflb .tree{width:230px;flex:none;overflow:auto;border:1px solid #4a4a4a;border-radius:6px;padding:6px}
.dflb .tree .row{display:flex;align-items:center;gap:6px;padding:3px 6px;border-radius:4px;cursor:pointer}.dflb .tree .row:hover{background:#2c2c2c}
.dflb .tree .row.sel{background:#2f3f55}.dflb .tree .row .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.dflb .tree button{padding:0 6px;font-size:12px}
.dflb .grid{flex:1;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px;align-content:start}
.dflb .card{background:#2a2a2a;border:1px solid #474747;border-radius:8px;overflow:hidden;display:flex;flex-direction:column}.dflb .card.sel{border-color:#6a9ad8}
.dflb .pic{aspect-ratio:3/4;background:#1e1e1e;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}
.dflb .pic img,.dflb .pic video{width:100%;height:100%;object-fit:cover;display:block}.dflb .pic .none{font-size:40px;opacity:.35}
.dflb .blur{filter:blur(22px);cursor:pointer}.dflb .base{position:absolute;left:6px;top:6px;background:#35584acc;color:#c8f0dc;border-radius:4px;padding:1px 6px;font-size:12px;font-weight:600}
.dflb .body{padding:7px 8px;display:flex;flex-direction:column;gap:5px;flex:1}.dflb .title{font-weight:600;color:#fff;word-break:break-word}
.dflb .muted{color:#999;font-size:12px;word-break:break-all}.dflb .words span{display:inline-block;background:#262626;border:1px solid #555;border-radius:4px;padding:0 5px;margin:0 3px 3px 0;font-size:12px;cursor:copy}
.dflb .buttons{display:flex;gap:5px;flex-wrap:wrap;margin-top:auto}.dflb .buttons button{padding:3px 8px;font-size:12px}.dflb .status{color:#9c9;font-size:13px;min-height:18px}
`;
function addStyle() {
  if (document.getElementById("dflb-style")) return;
  const style = document.createElement("style");
  style.id = "dflb-style";
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
const pathParts = (file) => file.split(/[\\/]/);
const folderOf = (file) => pathParts(file).slice(0, -1).join("/");
const shortName = (file) => pathParts(file).pop().replace(/\.[^.]+$/, "");

async function fetchList(kind) {
  const response = await api.fetchApi(`/diceforge/model-browser?kind=${kind}`);
  if (!response.ok) throw new Error(await response.text());
  return (await response.json()).files;
}
// Hash + Civitai lookup of one file (the Model info route), then its card data again from the list.
async function lookUp(kind, file) {
  const response = await api.fetchApi(`/diceforge/model-info?kind=${kind}&file=${encodeURIComponent(file)}`);
  if (!response.ok) throw new Error(await response.text());
  return (await fetchList(kind)).find((entry) => entry.file === file);
}

// target: what the buttons do (targetOf for a node's menu), or { pick(file), label, hint } from another extension (LoRA Stack): pick returns true
// to close the browser, or a message to show.
async function openBrowser(node, spec, target = targetOf(node, spec)) {
  addStyle();
  const { kind } = spec;
  const what = spec.one;
  let files = [], folder = "", selectedFile = target?.model?.value, stopLookUp = null;
  const search = element("input", { placeholder: "Search by file, name or trigger word…" });
  const base = element("select", {}, element("option", { value: "" }, "All base models"));
  const sort = element("select", {}, ...[["name", "Name"], ["new", "Newest first"], ["base", "Base model"]].map(([value, label]) => element("option", { value }, label)));
  const status = element("div", { class: "status" });
  const tree = element("div", { class: "tree" });
  const grid = element("div", { class: "grid" });
  const lookAll = element("button", { title: `Compute the hash of every ${what} not looked up yet and ask Civitai about it, one by one` }, "Look up all on Civitai");
  const back = element("div", { class: "dflb-back" });
  const onKey = (event) => { if (event.key === "Escape" && !document.querySelector(".dfmi-back")) { event.stopPropagation(); close(); } };
  function close() {
    stopLookUp?.();
    back.remove();
    document.removeEventListener("keydown", onKey, true);
  }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  const say = (text) => { status.textContent = text; };

  function replaceEntry(entry) {
    if (!entry) return;
    files = files.map((file) => (file.file === entry.file ? entry : file));
  }
  function action(entry) {
    if (target?.model) {
      const use = element("button", { class: "go", onclick: () => {
        setWidget(node, target.model, entry.file);
        selectedFile = entry.file;
        say(`${shortName(entry.file)} is now in ${target.model.name}.`);
        draw();
      } }, entry.file === target.model.value ? "In use" : "Use");
      use.disabled = entry.file === target.model.value;
      return [use];
    }
    if (target?.pick) {
      return [element("button", { class: "go", onclick: () => {
        const result = target.pick(entry.file);
        if (result === true) close();
        else if (typeof result === "string") say(result);
      } }, target.label)];
    }
    if (target?.triggers) {
      return [element("button", { class: "go", title: entry.trigger_words.length ? entry.trigger_words.join(", ") : "No trigger words known: look it up on Civitai or add your own in Info", onclick: () => {
        if (!entry.trigger_words.length) return say(`${shortName(entry.file)}: no trigger words known. Look it up on Civitai, or add your own in 🛈 Info.`);
        const field = insertIntoNode(node, entry.trigger_words.join(", "));
        say(`Added the trigger words of ${shortName(entry.file)} to ${field}.`);
      } }, "+ Triggers")];
    }
    return [];
  }
  function picture(entry) {
    const box = element("div", { class: "pic" });
    const url = entry.preview ? api.apiURL(`/diceforge/model-preview?kind=${kind}&file=${encodeURIComponent(entry.file)}&t=${entry.mtime}`) : entry.image?.url;
    if (!url) box.append(element("span", { class: "none" }, spec.icon));
    else {
      const media = !entry.preview && entry.image?.type === "video"
        ? element("video", { src: url, muted: "", loop: "", autoplay: "", playsinline: "" })
        : element("img", { src: url, loading: "lazy" });
      if (!entry.preview && (entry.image?.nsfwLevel ?? 1) >= 4) { // Civitai's R and up: blurred until clicked, as in Model info.
        media.classList.add("blur");
        media.addEventListener("click", () => media.classList.remove("blur"));
      }
      media.addEventListener("error", () => media.replaceWith(element("span", { class: "none", title: "The preview could not be loaded" }, spec.icon)));
      box.append(media);
    }
    if (entry.base_model) box.append(element("span", { class: "base" }, entry.base_model));
    return box;
  }
  function card(entry) {
    const words = element("div", { class: "words" }, ...entry.trigger_words.slice(0, 8).map((word) =>
      element("span", { title: "Click to copy", onclick: () => { navigator.clipboard?.writeText(word); say(`Copied "${word}".`); } }, word)));
    const lookUpButton = element("button", { onclick: async () => {
      lookUpButton.disabled = true;
      lookUpButton.textContent = "Looking up…";
      try {
        replaceEntry(await lookUp(kind, entry.file));
        draw();
      } catch (error) {
        say(`${shortName(entry.file)}: ${error.message}`);
        lookUpButton.textContent = "Look up failed";
      }
    } }, entry.checked ? "↻ Civitai" : "🔍 Civitai");
    const info = element("button", { onclick: () => {
      openModelInfo(kind, entry.file);
      const watch = setInterval(async () => { // When the Info dialog closes, the card shows what it looked up or what you typed there.
        if (document.querySelector(".dfmi-back")) return;
        clearInterval(watch);
        if (!back.isConnected) return;
        replaceEntry((await fetchList(kind)).find((item) => item.file === entry.file));
        draw();
      }, 300);
    } }, "🛈 Info");
    const link = entry.url ? [element("button", { onclick: () => window.open(entry.url, "_blank", "noopener") }, "Civitai ↗")] : [];
    const note = !entry.checked ? "Not looked up yet" : entry.found ? "" : "Not on Civitai";
    return element("div", { class: "card" + (entry.file === selectedFile ? " sel" : "") },
      picture(entry),
      element("div", { class: "body" },
        element("div", { class: "title" }, entry.name || shortName(entry.file)),
        element("div", { class: "muted" }, entry.file, ` · ${(entry.size / 1024 ** 2).toFixed(0)} MB`, note ? ` · ${note}` : ""),
        words,
        ...(entry.settings ? [element("div", { class: "muted", title: "Your recommended settings, from Model info" }, `⚙ ${entry.settings}`)] : []),
        element("div", { class: "buttons" }, ...action(entry), info, lookUpButton, ...link)));
  }
  function matches(entry) {
    const query = search.value.trim().toLowerCase();
    const text = [entry.file, entry.name, entry.base_model, ...entry.trigger_words].join(" ").toLowerCase();
    const inFolder = !folder || folderOf(entry.file) === folder || folderOf(entry.file).startsWith(folder + "/");
    return inFolder && (!base.value || entry.base_model === base.value) && (!query || query.split(/\s+/).every((word) => text.includes(word)));
  }
  function drawTree() {
    const counts = new Map([["", files.length]]);
    for (const entry of files) {
      const parts = pathParts(entry.file).slice(0, -1);
      parts.forEach((_, index) => { const path = parts.slice(0, index + 1).join("/"); counts.set(path, (counts.get(path) ?? 0) + 1); });
    }
    const folders = [...counts.keys()].sort((a, b) => a.localeCompare(b));
    tree.replaceChildren(...folders.map((path) => {
      const depth = path ? path.split("/").length : 0;
      const useFolder = target?.folder && path && target.folder.options.values.includes(path)
        ? [element("button", { title: `Pick the ${spec.plural} of ${path} in ${spec.randomName}`, onclick: (event) => {
            event.stopPropagation();
            setWidget(node, target.folder, path);
            say(`${spec.randomName} now picks from ${path}.`);
            drawTree();
          } }, target.folder.value === path ? "In use" : "Use folder")]
        : [];
      return element("div", { class: "row" + (path === folder ? " sel" : ""), style: `padding-left:${6 + depth * 12}px`, onclick: () => { folder = path; draw(); } },
        element("span", { class: "name" }, path ? `📁 ${path.split("/").pop()}` : `All ${spec.plural}`), element("span", { class: "muted" }, counts.get(path)), ...useFolder);
    }));
  }
  function draw() {
    const bases = [...new Set(files.map((entry) => entry.base_model).filter(Boolean))].sort();
    const chosen = base.value;
    base.replaceChildren(element("option", { value: "" }, "All base models"), ...bases.map((name) => element("option", { value: name }, name)));
    base.value = bases.includes(chosen) ? chosen : "";
    const order = {
      name: (a, b) => (a.name || shortName(a.file)).localeCompare(b.name || shortName(b.file)),
      new: (a, b) => b.mtime - a.mtime,
      base: (a, b) => (a.base_model || "~").localeCompare(b.base_model || "~") || shortName(a.file).localeCompare(shortName(b.file)),
    }[sort.value];
    const shown = files.filter(matches).sort(order);
    grid.replaceChildren(...(shown.length ? shown.map(card) : [element("div", { class: "muted" }, files.length ? `No ${what} matches.` : `No ${what} files: put them in ComfyUI/models/${kind}.`)]));
    const missing = files.filter((entry) => !entry.checked).length;
    lookAll.textContent = missing ? `Look up all on Civitai (${missing})` : "All looked up";
    lookAll.disabled = !missing && !stopLookUp;
    drawTree();
  }
  lookAll.addEventListener("click", async () => {
    if (stopLookUp) return stopLookUp();
    let stopped = false;
    stopLookUp = () => { stopped = true; };
    lookAll.textContent = "Stop";
    const queue = files.filter((entry) => !entry.checked).map((entry) => entry.file);
    for (const [index, file] of queue.entries()) {
      if (stopped) break;
      say(`Looking up ${index + 1} of ${queue.length}: ${shortName(file)} (hashing a large file takes a few seconds)…`);
      try { replaceEntry(await lookUp(kind, file)); } catch (error) { say(`${shortName(file)}: ${error.message}`); }
      if (back.isConnected) draw(), (lookAll.textContent = "Stop");
    }
    stopLookUp = null;
    if (back.isConnected) {
      say(stopped ? "Stopped." : "Done.");
      draw();
    }
  });
  for (const input of [search, base, sort]) input.addEventListener(input === search ? "input" : "change", draw);
  const hint = target?.pick ? target.hint : target?.model ? `Use puts a ${what} in ${target.model.name}.` : target?.folder ? `Use folder sets the folder ${spec.randomName} picks from.` : target?.triggers ? `+ Triggers inserts a ${what}'s trigger words where the cursor was in the prompt.` : "";
  back.append(element("div", { class: "dflb" },
    element("h2", {}, `${spec.title} Browser`),
    element("div", { class: "top" }, search, base, sort, lookAll, element("button", { onclick: close }, "Close")),
    element("div", { class: "top" }, element("span", { class: "muted" }, hint), status),
    element("div", { class: "main" }, tree, grid)));
  document.body.append(back);
  say("Loading…");
  try {
    files = await fetchList(kind);
    say("");
  } catch (error) {
    say(`Could not list the ${spec.plural}: ${error.message}`);
  }
  draw();
  search.focus();
  grid.querySelector(".card.sel")?.scrollIntoView({ block: "center" });
}

app.registerExtension({
  name: "DiceForge.ModelBrowser",
  getNodeMenuItems(node) {
    return BROWSERS.filter((spec) => targetOf(node, spec)).map((spec) => ({ content: `${spec.icon} ${spec.title} Browser`, callback: () => openBrowser(node, spec) }));
  },
});

export { openBrowser as openModelBrowser, BROWSERS };
