import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, background, element } from "./dom.js";

// "Find on Civitai" in the LoRA Browser (the Create of its files): search Civitai's LoRAs, pick a version, download it into a LoRA folder. The server
// (model_manager.py) does the download, checks it against Civitai's sha256 and saves its Civitai data and a preview, so the browser shows it at once.
// Downloads keep running when this dialog closes; it shows them again when opened.
const BASES = ["SD 1.5", "SDXL 1.0", "Pony", "Illustrious", "NoobAI", "Flux.1 D", "Flux.1 S", "SD 3.5", "Wan Video", "Hunyuan Video"];
const SORTS = ["Highest Rated", "Most Downloaded", "Newest"];

const STYLE = `
.dfcv-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10002;display:flex;align-items:center;justify-content:center}
.dfcv{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(1300px,95vw);height:min(880px,92vh);display:flex;flex-direction:column;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dfcv h2{margin:0 0 10px;font-size:20px;color:#fff}.dfcv .top{display:flex;gap:8px;margin-bottom:8px;align-items:center;flex-wrap:wrap}
.dfcv input,.dfcv select{background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:6px 8px;font:inherit}.dfcv .top input.query{flex:1;min-width:180px}
.dfcv button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:5px 12px;cursor:pointer;font:inherit}.dfcv button:hover{background:#2c2c2c}
.dfcv button:disabled{opacity:.5;cursor:default}.dfcv button.go{border-color:#4a7a4a;color:#bfe8bf}.dfcv label{display:flex;gap:5px;align-items:center}
.dfcv .grid{flex:1;overflow:auto;display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:10px;align-content:start}
.dfcv .card{background:#2a2a2a;border:1px solid #474747;border-radius:8px;overflow:hidden;display:flex;flex-direction:column}
.dfcv .pic{aspect-ratio:3/4;background:#1e1e1e;display:flex;align-items:center;justify-content:center;overflow:hidden;position:relative}
.dfcv .pic img,.dfcv .pic video{width:100%;height:100%;object-fit:cover;display:block}.dfcv .pic .none{font-size:40px;opacity:.35}.dfcv .blur{filter:blur(22px);cursor:pointer}
.dfcv .base{position:absolute;left:6px;top:6px;background:#35584acc;color:#c8f0dc;border-radius:4px;padding:1px 6px;font-size:12px;font-weight:600}
.dfcv .body{padding:7px 8px;display:flex;flex-direction:column;gap:5px;flex:1}.dfcv .title{font-weight:600;color:#fff;word-break:break-word}
.dfcv .muted{color:#999;font-size:12px;word-break:break-word}.dfcv .words span{display:inline-block;background:#262626;border:1px solid #555;border-radius:4px;padding:0 5px;margin:0 3px 3px 0;font-size:12px}
.dfcv .buttons{display:flex;gap:5px;flex-wrap:wrap;margin-top:auto}.dfcv .buttons button{padding:3px 8px;font-size:12px}.dfcv .status{color:#9c9;font-size:13px;min-height:18px}
.dfcv .card select{width:100%;font-size:12px;padding:3px 4px}.dfcv .installed{color:#9c9;font-size:12px}.dfcv .more{grid-column:1/-1;justify-self:center}
.dfcv .jobs{max-height:140px;overflow:auto;border-top:1px solid #4a4a4a;margin-top:8px;padding-top:6px;display:flex;flex-direction:column;gap:4px}.dfcv .jobs:empty{display:none}
.dfcv .job{display:flex;gap:8px;align-items:center;font-size:13px}.dfcv .job .name{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dfcv .job progress{width:180px}.dfcv .job.error .state{color:#f0a0a0}.dfcv .job.done .state{color:#9c9}.dfcv .job button{padding:1px 8px;font-size:12px}
`;
const addStyle = () => addStyleOnce("dfcv-style", STYLE);
const megabytes = (bytes) => `${(bytes / 1024 ** 2).toFixed(bytes < 10 * 1024 ** 2 ? 1 : 0)} MB`;

async function call(path, options) {
  const response = await api.fetchApi(path, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

// kind: the model kind; folders: the existing folders, offered for "Save to"; base: the connected model's base model, to search for it first;
// onChange(): called when a download is done, so the opener shows the new file.
export async function openCivitaiSearch({ kind = "loras", folders = [], base = "", onChange = () => {} } = {}) {
  addStyle();
  const query = element("input", { class: "query", placeholder: "Search LoRAs on Civitai…" });
  const baseSelect = element("select", { title: "Base model" }, element("option", { value: "" }, "All base models"), ...BASES.map((name) => element("option", { value: name }, name)));
  baseSelect.value = BASES.includes(base) ? base : "";
  const sort = element("select", { title: "Order" }, ...SORTS.map((name) => element("option", { value: name }, name)));
  const nsfw = element("input", { type: "checkbox" });
  const folderList = element("datalist", { id: "dfcv-folders" }, ...folders.map((folder) => element("option", { value: folder })));
  const folder = element("input", { placeholder: "(top folder)", list: "dfcv-folders", title: "The folder (inside models/loras) the downloads go to; / for subfolders" });
  const keyButton = element("button", { title: "Some LoRAs can only be downloaded with your Civitai API key (Civitai → Account settings → API keys)" }, "🔑 API key");
  const status = element("div", { class: "status" });
  const grid = element("div", { class: "grid" });
  const jobsBox = element("div", { class: "jobs" });
  const back = element("div", { class: "dfcv-back" });
  let items = [], next = null, searchRun = 0, polling = null, knownDone = new Set();
  const say = (text) => { status.textContent = text; };
  const onKey = (event) => { if (event.key === "Escape") { event.stopPropagation(); close(); } };
  function close() {
    clearTimeout(polling);
    polling = null;
    back.remove();
    document.removeEventListener("keydown", onKey, true);
  }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);

  async function showKey() {
    try {
      const key = await call("/diceforge/civitai/key");
      keyButton.textContent = key.set ? "🔑 API key ✓" : "🔑 API key";
      keyButton.dataset.source = key.source ?? "";
    } catch { /* The search still works without it. */ }
  }
  keyButton.addEventListener("click", async () => {
    if (keyButton.dataset.source === "environment") return say("The API key comes from CIVITAI_API_KEY in ComfyUI's environment: change it there.");
    const key = prompt("Your Civitai API key (Civitai → Account settings → API keys). It is kept in the ComfyUI user folder and only sent to Civitai. Empty removes it:", "");
    if (key === null) return;
    try {
      const result = await call("/diceforge/civitai/key", { method: "POST", body: JSON.stringify({ key: key.trim() }) });
      say(result.set ? "API key saved." : "API key removed.");
    } catch (error) { say(error.message); }
    await showKey();
  });

  function picture(version) {
    const box = element("div", { class: "pic" });
    const image = version?.images?.[0];
    if (!image) box.append(element("span", { class: "none" }, "🎴"));
    else {
      const media = image.type === "video" ? element("video", { src: image.url, muted: "", loop: "", autoplay: "", playsinline: "" }) : element("img", { src: image.url, loading: "lazy" });
      if ((image.nsfwLevel ?? 1) >= 4) { // Civitai's R and up: blurred until clicked.
        media.classList.add("blur");
        media.addEventListener("click", () => media.classList.remove("blur"));
      }
      media.addEventListener("error", () => media.replaceWith(element("span", { class: "none" }, "🎴")));
      box.append(media);
    }
    if (version?.base_model) box.append(element("span", { class: "base" }, version.base_model));
    return box;
  }
  function card(item) {
    const box = element("div", { class: "card" });
    const draw = () => {
      const version = item.versions[item.selected ?? 0]; // Kept on the item: a redraw (a download done) shows the same version.
      const versions = item.versions.length > 1
        ? [element("select", { title: "Version", onchange: (event) => { item.selected = Number(event.target.value); draw(); } },
            ...item.versions.map((entry, index) => element("option", { value: index, ...(entry === version ? { selected: "" } : {}) }, `${entry.name}${entry.base_model ? ` · ${entry.base_model}` : ""}`)))]
        : [];
      const download = element("button", { class: "go", onclick: () => background(start(item, version)) }, "⬇ Download");
      download.disabled = !version?.file || !!version.installed;
      const state = !version?.file ? element("div", { class: "muted" }, "No file ComfyUI loads")
        : version.installed ? element("div", { class: "installed", title: version.installed }, `✓ Already here: ${version.installed}`)
        : element("div", { class: "muted" }, `${version.file.name} · ${megabytes(version.file.size)}${version.early_access ? " · early access" : ""}`);
      box.replaceChildren(picture(version),
        element("div", { class: "body" },
          element("div", { class: "title" }, item.name),
          element("div", { class: "muted" }, `${item.creator ? `by ${item.creator} · ` : ""}⬇ ${item.downloads.toLocaleString()} · 👍 ${item.likes.toLocaleString()}`),
          ...versions,
          element("div", { class: "words" }, ...(version?.trigger_words ?? []).slice(0, 6).map((word) => element("span", {}, word))),
          state,
          element("div", { class: "buttons" }, download, element("button", { onclick: () => window.open(item.url + (version ? `?modelVersionId=${version.id}` : ""), "_blank", "noopener") }, "Civitai ↗"))));
    };
    box.redraw = draw;
    draw();
    return box;
  }
  function drawGrid() {
    const more = next ? [element("button", { class: "more", onclick: () => background(search(true)) }, "Load more")] : [];
    grid.replaceChildren(...(items.length ? items.map(card) : [element("div", { class: "muted" }, "No LoRA found: try other words or another base model.")]), ...more);
  }
  async function search(more = false) {
    const run = ++searchRun;
    say(more ? "Loading more…" : "Searching Civitai…");
    const params = new URLSearchParams({ kind, query: query.value.trim(), base: baseSelect.value, sort: sort.value, nsfw: nsfw.checked ? "1" : "0" });
    if (more && next) params.set("cursor", next);
    try {
      const result = await call(`/diceforge/civitai/search?${params}`);
      if (run !== searchRun) return; // A newer search was started meanwhile.
      items = more ? [...items, ...result.items] : result.items;
      next = result.next;
      say(`${items.length} LoRA${items.length === 1 ? "" : "s"}${next ? ", more with Load more" : ""}.`);
      drawGrid();
    } catch (error) {
      if (run === searchRun) say(error.message);
    }
  }
  async function start(item, version) {
    try {
      const job = await call("/diceforge/civitai/download", { method: "POST", body: JSON.stringify({ kind, version_id: version.id, folder: folder.value.trim() }) });
      say(`Downloading ${job.file}…`);
      await poll();
    } catch (error) { say(error.message); }
  }
  // The downloads, until none is running: progress, Stop, and Clear for finished ones. A finished one marks its card and tells the opener.
  async function poll() {
    clearTimeout(polling);
    let jobs = [];
    try { jobs = (await call("/diceforge/civitai/downloads")).jobs; } catch { /* Shown again on the next poll. */ }
    if (!back.isConnected) return;
    jobsBox.replaceChildren(...jobs.map((job) => {
      const percent = job.total ? Math.min(100, Math.round((job.done / job.total) * 100)) : 0;
      const state = { downloading: `${percent}% · ${megabytes(job.done)}${job.total ? ` of ${megabytes(job.total)}` : ""}`, done: "✓ Done", cancelled: "Stopped", error: job.error }[job.status] ?? job.status;
      return element("div", { class: `job ${job.status}` },
        element("span", { class: "name", title: job.file }, `${job.model}${job.version ? ` · ${job.version}` : ""} → ${job.file}`),
        ...(job.status === "downloading" ? [element("progress", { max: 100, value: percent })] : []),
        element("span", { class: "state" }, state),
        element("button", { onclick: async () => { await api.fetchApi(`/diceforge/civitai/downloads?id=${job.id}`, { method: "DELETE" }); await poll(); } },
          job.status === "downloading" ? "Stop" : "Clear"));
    }));
    let changed = false;
    for (const job of jobs.filter((entry) => entry.status === "done" && !knownDone.has(entry.id))) {
      knownDone.add(job.id);
      changed = true;
      say(`Downloaded ${job.file}: it is in the LoRA Browser and the LoRA lists.`);
      for (const item of items) for (const version of item.versions) if (version.id === job.version_id) version.installed = job.file;
    }
    if (changed) {
      drawGrid();
      onChange();
      background(app.refreshComboInNodes?.()); // The LoRA lists of the loader nodes get the new file.
    }
    if (jobs.some((job) => job.status === "downloading")) polling = setTimeout(() => background(poll()), 700);
  }

  query.addEventListener("keydown", (event) => { if (event.key === "Enter") background(search()); });
  for (const input of [baseSelect, sort, nsfw]) input.addEventListener("change", () => background(search()));
  back.append(element("div", { class: "dfcv" },
    element("h2", {}, "Find LoRAs on Civitai"),
    element("div", { class: "top" }, query, baseSelect, sort, element("label", { title: "Also show LoRAs Civitai marks as NSFW" }, nsfw, "NSFW"),
      element("button", { class: "go", onclick: () => background(search()) }, "Search"), keyButton, element("button", { onclick: close }, "Close")),
    element("div", { class: "top" }, element("span", { class: "muted" }, "Save to folder:"), folder, folderList, status),
    grid, jobsBox));
  document.body.append(back);
  query.focus();
  // Downloads finished before this dialog opened are not news.
  try { for (const job of (await call("/diceforge/civitai/downloads")).jobs) if (job.status === "done") knownDone.add(job.id); } catch { /* No list yet. */ }
  await Promise.all([showKey(), poll(), search()]);
}
