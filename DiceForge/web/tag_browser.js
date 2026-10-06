import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { addStyleOnce, background, element } from "./dom.js";
import { compact } from "./civitai_meta.js";
import { tagText } from "./tag_autocomplete.js";
import { fieldsOf, insertIntoNode, isPromptNode } from "./wildcards.js";
import { recall, remember, scrollBack } from "./window_memory.js";

// Tag Browser (CLIP Dual Text Encode's menu): the Danbooru / e621 tags of the downloaded lists (tag_autocomplete.py), searched by name or alias,
// by type (characters, artists, series, general, meta) or your ★ favorites, most used first or by name. + Add puts a tag where the cursor was in
// the prompts (as the autocomplete writes it: spaces, escaped parentheses), − Neg at the end of the negative prompt; ↗ opens its wiki page on Danbooru, or
// e621 for a tag of an e621 list (what the tag means, how it's used).
// A tag's wiki page on its site: e621 for the tags of an e621 list, else Danbooru (the name as the address: ? and / escaped).
const WIKIS = { e621: ["e621", (tag) => `https://e621.net/wiki_pages/show_or_new?title=${encodeURIComponent(tag)}`],
  danbooru: ["Danbooru", (tag) => `https://danbooru.donmai.us/wiki_pages/${encodeURIComponent(tag)}`] };
const wikiOf = (tag) => WIKIS[tag.site] || WIKIS.danbooru;
const STYLE = `
.dftb-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dftb{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(980px,95vw);height:min(820px,90vh);display:flex;flex-direction:column;gap:8px;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dftb h2{margin:0;font-size:20px;color:#fff}.dftb .top{display:flex;gap:8px;align-items:center;flex-wrap:wrap}
.dftb input,.dftb select{background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:6px 8px;font:inherit}.dftb .top input{flex:1;min-width:180px}
.dftb .types{display:flex;gap:5px;flex-wrap:wrap}.dftb .types button.on{background:#2f3f55;border-color:#6a9ad8;color:#fff}
.dftb button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit}.dftb button:hover{background:#2c2c2c}
.dftb .list{flex:1;overflow:auto;border:1px solid #4a4a4a;border-radius:6px}
.dftb .row{display:flex;align-items:center;gap:8px;padding:4px 8px;border-bottom:1px solid #3a3a3a}.dftb .row:hover{background:#2c2c2c}
.dftb .row .name{flex:1;min-width:0}.dftb .row .name b{color:#fff;font-weight:600}.dftb .row .aliases{color:#888;font-size:12px;margin-left:6px}
.dftb .row .count{color:#9c9;font-size:12px;width:52px;text-align:right}.dftb .row .kind{font-size:12px;color:#aaa;width:78px}
.dftb .row button{padding:1px 8px;font-size:12px}.dftb .row button.add{border-color:#4a7a4a;color:#bfe8bf}.dftb .row button.neg{border-color:#7a4a4a;color:#f0c0c0}
.dftb .row button.fav{border:none;background:none;font-size:16px;color:#888;padding:0 2px}.dftb .row button.fav.on{color:#ffd24a}
.dftb .row a{color:#9cc8ff;text-decoration:none;font-size:13px}.dftb .status{color:#9c9;font-size:13px;min-height:18px}.dftb .more{margin:8px auto;display:block}
.dftb .empty{color:#999;padding:16px}
`;
const TYPES = [["", "All"], ["general", "General"], ["character", "👤 Characters"], ["copyright", "©️ Series"], ["artist", "🎨 Artists"], ["meta", "⚙️ Meta"], ["favorites", "★ Favorites"]];
const KIND_NAMES = { general: "general", character: "👤 character", copyright: "©️ series", artist: "🎨 artist", meta: "⚙️ meta" };
const PAGE = 100;
async function request(path, options) {
  const response = await api.fetchApi(path, options);
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function openTagBrowser(node) {
  addStyleOnce("dftb-style", STYLE);
  const last = recall("tags"); // Opens where it was closed: the search, the type, the order, the scrolling.
  let kind = TYPES.some(([value]) => value === last.kind) ? last.kind : "", tags = [], total = 0, loading = 0;
  const search = element("input", { placeholder: "Search tags or aliases (spaces or underscores)…" });
  const sort = element("select", {}, element("option", { value: "count" }, "Most used"), element("option", { value: "name" }, "Name"));
  search.value = typeof last.search === "string" ? last.search : "";
  sort.value = last.sort === "name" ? "name" : "count";
  const types = element("div", { class: "types" });
  const list = element("div", { class: "list" });
  const status = element("div", { class: "status" });
  const say = (text) => { status.textContent = text; };
  const back = element("div", { class: "dftb-back" });
  const onKey = (event) => { if (event.key === "Escape") { event.stopPropagation(); close(); } };
  function close() {
    remember("tags", { search: search.value, kind, sort: sort.value, scroll: list.scrollTop });
    back.remove();
    document.removeEventListener("keydown", onKey, true);
  }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);

  async function load(more = false) {
    const requestId = ++loading;
    const query = new URLSearchParams({ q: search.value, type: kind, sort: sort.value, offset: String(more ? tags.length : 0), limit: String(PAGE) });
    let page;
    try {
      page = await request(`/diceforge/tags/browse?${query}`);
    } catch (error) {
      return say(error.message);
    }
    if (requestId !== loading) return; // Typed on meanwhile: the newer answer draws.
    tags = more ? [...tags, ...page.tags] : page.tags;
    total = page.total;
    draw(page.ready);
  }
  async function setFavorite(tag, favorite) {
    try {
      await request("/diceforge/tags/favorite", { method: "POST", body: JSON.stringify({ tag: tag.tag, favorite }) });
    } catch (error) {
      return say(error.message);
    }
    tag.favorite = favorite;
    if (kind === "favorites" && !favorite) await load();
    else draw(true);
  }
  function add(tag, field) {
    const where = insertIntoNode(node, tagText(tag.tag), field);
    say(`Added ${tagText(tag.tag)} to the ${where} prompt.`);
  }
  function row(tag) {
    return element("div", { class: "row" },
      element("button", { class: "fav" + (tag.favorite ? " on" : ""), title: tag.favorite ? "A favorite: click to remove the star" : "Add to favorites",
        onclick: () => background(setFavorite(tag, !tag.favorite)) }, tag.favorite ? "★" : "☆"),
      element("span", { class: "name", title: tag.aliases.length ? `Also: ${tag.aliases.join(", ")}` : "" }, element("b", {}, tag.tag),
        ...(tag.aliases.length ? [element("span", { class: "aliases" }, tag.aliases.slice(0, 3).join(", "))] : [])),
      element("span", { class: "kind" }, KIND_NAMES[tag.type] ?? tag.type),
      element("span", { class: "count", title: `${tag.count.toLocaleString()} posts` }, compact(tag.count)),
      element("button", { class: "add", title: "Put it where the cursor was in the prompts", onclick: () => add(tag) }, "+ Add"),
      ...(fieldsOf(node)?.includes("negative") ? [element("button", { class: "neg", title: "Put it in the negative prompt", onclick: () => add(tag, "negative") }, "− Neg")] : []),
      element("a", { class: "wiki", href: wikiOf(tag)[1](tag.tag), target: "_blank", rel: "noopener", title: `Open its wiki page on ${wikiOf(tag)[0]}` }, "↗"));
  }
  function draw(ready) {
    types.replaceChildren(...TYPES.map(([value, label]) => element("button", { class: value === kind ? "on" : "", onclick: () => { kind = value; background(load()); } }, label)));
    if (!ready) {
      list.replaceChildren(element("div", { class: "empty" }, "No tag list yet: download one from the node's menu (🏷 Tag autocomplete → ⬇ Download: Danbooru)."));
      return;
    }
    const rows = tags.map(row);
    if (tags.length < total) rows.push(element("button", { class: "more", onclick: () => background(load(true)) }, `Show more (${(total - tags.length).toLocaleString()} left)`));
    list.replaceChildren(...(rows.length ? rows : [element("div", { class: "empty" }, kind === "favorites" ? "No favorites yet: ☆ next to a tag adds it." : "No tag matches.")]));
    say(`${total.toLocaleString()} tag${total === 1 ? "" : "s"}`);
  }
  let typing = null;
  search.addEventListener("input", () => { clearTimeout(typing); typing = setTimeout(() => background(load()), 150); });
  sort.addEventListener("change", () => background(load()));
  back.append(element("div", { class: "dftb" },
    element("h2", {}, "Tag Browser"),
    element("div", { class: "top" }, search, sort, element("button", { onclick: close }, "Close")),
    types, list, status));
  document.body.append(back);
  search.focus();
  search.setSelectionRange(search.value.length, search.value.length);
  await load();
  scrollBack(list, last.scroll);
}

app.registerExtension({
  name: "DiceForge.TagBrowser",
  getNodeMenuItems(node) {
    return isPromptNode(node) ? [{ content: "🏷 Tag Browser", callback: () => background(openTagBrowser(node)) }] : [];
  },
});
