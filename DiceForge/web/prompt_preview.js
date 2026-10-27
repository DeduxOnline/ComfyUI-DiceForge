import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, asking, element } from "./dom.js";
import { setField } from "./wildcards.js";

// Prompt history of CLIP Dual Text Encode (a window, from the node's right-click menu): the last runs' prompts as encoded (20, plus the pinned ones), newest first,
// each with the images its run made (Save Image, Preview Image, VAE Decode + Save... in the same workflow). From an entry: ↺ Seed puts back its
// prompts, seed and mode (with control after generate on fixed), so the next run gives the same prompts again; Use text puts the prompts as encoded
// in the fields, every choice made; 📌 keeps it past the 20; ✕ removes it. The history is kept in the node's properties, so it travels with the workflow, but not into the images a run makes (withoutRunData).
const NODE_TYPE = "DiceForgeCLIPDualTextEncode";
const STYLE = `
.dfph-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dfph{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(1100px,95vw);height:min(860px,92vh);display:flex;flex-direction:column;gap:8px;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dfph h2{margin:0;font-size:20px;color:#fff}.dfph .top{display:flex;gap:8px;align-items:center}.dfph .top .muted{flex:1}.dfph .muted{color:#999;font-size:13px}
.dfph button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:3px 9px;cursor:pointer;font:inherit;font-size:13px}.dfph button:hover{background:#2c2c2c}
.dfph .list{flex:1;overflow:auto;display:flex;flex-direction:column;gap:8px;padding-right:4px}
.dfph .entry{display:flex;gap:10px;border:1px solid #4a4a4a;border-radius:8px;padding:8px;background:#2e2e2e}.dfph .entry.pinned{border-color:#8a7a3a}
.dfph .shots{display:flex;gap:4px;flex:none}.dfph .shots img{width:120px;height:120px;object-fit:cover;border-radius:6px;background:#1e1e1e;cursor:zoom-in;display:block}
.dfph .shots .none{width:120px;height:120px;border-radius:6px;background:#262626;color:#777;font-size:12px;display:flex;align-items:center;justify-content:center;text-align:center;padding:6px;box-sizing:border-box}
.dfph .body{flex:1;min-width:0;display:flex;flex-direction:column;gap:4px}.dfph .meta{display:flex;gap:5px;align-items:center;color:#999;font-size:13px}.dfph .meta .when{flex:1}
.dfph .text{white-space:pre-wrap;word-break:break-word;color:#ddd;font-size:13px;max-height:90px;overflow:auto}.dfph .neg{color:#b99;font-size:12px;white-space:pre-wrap;word-break:break-word;max-height:48px;overflow:auto}
.dfph button.on{border-color:#b8962e;color:#ffd24a}.dfph .empty{color:#999;padding:16px}
`;
const HISTORY = 20; // Kept runs, the pinned ones not counted.
const IMAGES = 4; // Images kept per run.
// The history with a new run first: a run like the newest one (a cached run, or the same seed again) is not added twice; past HISTORY, the oldest
// unpinned ones go.
export function addToHistory(history, entry, limit = HISTORY) {
  const list = Array.isArray(history) ? history.filter((item) => item && typeof item === "object") : [];
  const same = (item) => ["positive", "negative", "seed", "seed_mode", "source_positive", "source_negative"].every((key) => item[key] === entry[key]);
  if (list[0] && same(list[0])) return list;
  const next = [entry, ...list];
  let unpinned = 0;
  return next.filter((item) => item.pinned || ++unpinned <= limit);
}
// An entry with one more image of its run (the newest last, at most IMAGES; the same file once).
export function withImage(entry, image) {
  const shot = { filename: String(image.filename), subfolder: String(image.subfolder ?? ""), type: String(image.type ?? "output") };
  const images = (Array.isArray(entry.images) ? entry.images : []).filter((item) => item.filename !== shot.filename || item.subfolder !== shot.subfolder || item.type !== shot.type);
  return { ...entry, images: [...images, shot].slice(-IMAGES) };
}
const viewURL = (shot) => api.apiURL(`/view?${new URLSearchParams({ filename: shot.filename, subfolder: shot.subfolder, type: shot.type })}`);
const widget = (node, name) => node.widgets?.find((item) => item.name === name);
function setValue(node, name, value) {
  const item = widget(node, name);
  if (!item) return;
  item.value = value;
  item.callback?.(value);
}
function saveHistory(node, history) {
  node.properties ??= {};
  node.properties.dice_forge_history = history;
  node.graph?.setDirtyCanvas?.(true, true);
}

// The runs being made: which history entry of which node each queued prompt belongs to, so the images it makes go to that entry.
// A run's images can come before its prompts (another branch of the workflow ran first): they wait in shots until the entry is known.
let runningPrompt = null;
const runs = new Map(); // prompt_id -> [{ node, time }]
const shots = new Map(); // prompt_id -> [image]
function addImage(node, time, image) {
  const history = node.properties?.dice_forge_history;
  const index = Array.isArray(history) ? history.findIndex((item) => item?.time === time) : -1;
  if (index < 0) return;
  const next = [...history];
  next[index] = withImage(history[index], image);
  saveHistory(node, next);
}
function link(promptId, node, entry) {
  if (!promptId || !entry?.time) return;
  const list = runs.get(promptId) ?? [];
  if (list.some((item) => item.node === node)) return;
  list.push({ node, time: entry.time });
  runs.set(promptId, list);
  for (const image of shots.get(promptId) ?? []) addImage(node, entry.time, image);
  while (runs.size > 50) runs.delete(runs.keys().next().value);
}
const graphNode = (id) => app.graph?.getNodeById?.(Number(id)) ?? app.graph?.getNodeById?.(id);
api.addEventListener("execution_start", ({ detail }) => { runningPrompt = detail?.prompt_id ?? null; });
api.addEventListener("execution_cached", ({ detail }) => { // The prompts came from the cache: the run is the newest entry's again.
  for (const id of detail?.nodes ?? []) {
    const node = graphNode(id);
    if (node?.comfyClass === NODE_TYPE) link(detail.prompt_id, node, node.properties?.dice_forge_history?.[0]);
  }
});
api.addEventListener("executed", ({ detail }) => {
  const image = detail?.output?.images?.find((item) => item?.filename);
  if (!image || !detail.prompt_id) return;
  shots.set(detail.prompt_id, [...(shots.get(detail.prompt_id) ?? []), image].slice(-IMAGES));
  while (shots.size > 50) shots.delete(shots.keys().next().value);
  for (const { node, time } of runs.get(detail.prompt_id) ?? []) addImage(node, time, image);
});

export function openHistory(node) {
  addStyleOnce("dfpp-style", STYLE);
  const list = element("div", { class: "list" });
  const back = element("div", { class: "dfph-back" });
  const onKey = (event) => { if (asking()) return; if (event.key === "Escape") { event.stopPropagation(); close(); } };
  let shown;
  const timer = setInterval(() => { if (node.properties?.dice_forge_history !== shown) draw(); }, 400); // New runs and images show up.
  function close() {
    clearInterval(timer);
    back.remove();
    document.removeEventListener("keydown", onKey, true);
  }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  const update = (change) => {
    const history = [...(node.properties?.dice_forge_history ?? [])];
    change(history);
    saveHistory(node, history);
    draw();
  };
  function entry(item, index) {
    const when = item.time ? new Date(item.time).toLocaleString([], { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "";
    const shots = (item.images ?? []).map((shot) => {
      const picture = element("img", { src: viewURL(shot), loading: "lazy", title: "Click to open it full size" });
      picture.addEventListener("click", () => window.open(viewURL(shot), "_blank", "noopener"));
      picture.addEventListener("error", () => picture.replaceWith(element("div", { class: "none" }, "A preview, cleared since (ComfyUI keeps previews until a restart)")));
      return picture;
    });
    return element("div", { class: "entry" + (item.pinned ? " pinned" : ""), "data-index": index },
      element("div", { class: "shots" }, ...(shots.length ? shots : [element("div", { class: "none" }, "No image from this run")])),
      element("div", { class: "body" },
        element("div", { class: "meta" },
          element("span", { class: "when" }, `${when} · seed ${item.seed} (${[item.seed_mode, item.note].filter(Boolean).join(", ")})`),
          element("button", { class: "pin" + (item.pinned ? " on" : ""), title: item.pinned ? "Pinned: kept past the last 20 (click to unpin)" : "Pin: keep it past the last 20",
            onclick: () => update((history) => { history[index] = { ...item, pinned: !item.pinned }; }) }, "📌"),
          element("button", { class: "reseed", // Every seed mode gives the same prompts for the same seed.
            title: "Put back its prompts, seed and mode (control after generate: fixed): the next run gives these prompts again",
            onclick: () => {
              if (item.source_positive != null) setField(node, "positive", item.source_positive);
              if (item.source_negative != null) setField(node, "negative", item.source_negative);
              setValue(node, "seed", item.seed);
              setValue(node, "seed_mode", item.seed_mode);
              setValue(node, "control_after_generate", "fixed");
              node.setDirtyCanvas?.(true, true);
            } }, "↺ Seed"),
          element("button", { class: "use-text", title: "Put these prompts as encoded in the fields: every choice and wildcard fixed",
            onclick: () => { setField(node, "positive", item.positive ?? ""); setField(node, "negative", item.negative ?? ""); } }, "Use text"),
          element("button", { class: "forget", title: "Remove it from the history", onclick: () => update((history) => { history.splice(index, 1); }) }, "✕")),
        element("div", { class: "text" }, item.positive || "(empty)"),
        ...(item.negative ? [element("div", { class: "neg" }, `negative: ${item.negative}`)] : [])));
  }
  function draw() {
    shown = node.properties?.dice_forge_history;
    const history = Array.isArray(shown) ? shown : [];
    list.replaceChildren(...(history.length ? history.map((item, index) => entry(item, index)) : [element("div", { class: "empty" }, "No runs yet: run the workflow, and its prompts and images are kept here.")]));
    count.textContent = `${history.length} run${history.length === 1 ? "" : "s"}, newest first`;
  }
  const count = element("span", { class: "muted" });
  back.append(element("div", { class: "dfph" }, element("h2", {}, `Prompt history · ${node.title || "CLIP Dual Text Encode"}`),
    element("div", { class: "top" }, count, element("button", { onclick: close }, "Close")), list));
  document.body.append(back);
  draw();
}

// What nodes keep of their last runs: CLIP Dual Text Encode's prompt history, Danbooru Tag Enhancer's last prompt and post, Random Image's
// picked file. A run's workflow goes without it: ComfyUI saves that one in the images the run makes (their metadata), where it would hand
// earlier prompts and file names to whoever gets a picture. The graph, the tab's autosave and a saved workflow keep it; a run opened again
// from the queue or from its picture doesn't have it.
const RUN_DATA = ["dice_forge_history", "dice_forge_danbooru", "dice_forge_image"];
export function withoutRunData(workflow) {
  if (!workflow) return workflow;
  const clean = (nodes) => nodes?.map((node) => RUN_DATA.some((key) => key in (node.properties ?? {}))
    ? { ...node, properties: Object.fromEntries(Object.entries(node.properties).filter(([key]) => !RUN_DATA.includes(key))) } : node);
  const subgraphs = workflow.definitions?.subgraphs;
  return { ...workflow, nodes: clean(workflow.nodes),
    ...(subgraphs && { definitions: { ...workflow.definitions, subgraphs: subgraphs.map((graph) => ({ ...graph, nodes: clean(graph.nodes) })) } }) };
}

app.registerExtension({
  name: "DiceForge.PromptPreview",
  setup() {
    const queuePrompt = api.queuePrompt;
    api.queuePrompt = function (number, data, ...rest) {
      // The same object goes on: another extension's wrapper may change its output, which the frontend reads back after the call.
      if (data?.workflow) data.workflow = withoutRunData(data.workflow);
      return queuePrompt.call(this, number, data, ...rest);
    };
  },
  getNodeMenuItems(node) {
    return node.comfyClass === NODE_TYPE ? [{ content: "🕘 Prompt history", callback: () => openHistory(node) }] : [];
  },
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    const text = (name) => String(widget(node, name)?.value ?? "");
    const onExecuted = node.onExecuted;
    node.onExecuted = function (output) {
      const result = output?.dice_forge_prompts?.[0];
      if (result) {
        node.properties ??= {};
        const entry = { ...result, source_positive: text("positive"), source_negative: text("negative"), time: Date.now() };
        node.properties.dice_forge_history = addToHistory(node.properties.dice_forge_history, entry);
        link(runningPrompt, node, node.properties.dice_forge_history[0]); // The images of this run go to its entry.
      }
      return onExecuted?.apply(this, arguments);
    };
  },
});
