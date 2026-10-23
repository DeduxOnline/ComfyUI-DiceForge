import { app } from "../../scripts/app.js";
import { addStyleOnce, asking, background, element } from "./dom.js";
import { compact } from "./civitai_meta.js";
import { tagText } from "./tag_autocomplete.js";
import { cursorField, fieldsOf, insertIntoNode, isPromptNode } from "./wildcards.js";
import { keysButton, keysOnQuestion, moveCursor, slashToSearch, typingIn } from "./menu.js";
import { keepSize, recall, remember, scrollBack } from "./window_memory.js";
import { request } from "./comfy.js";

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
.dftb .empty{color:#999;padding:16px}.dftb .row .has{color:#7fd47f;font-weight:700;cursor:help}.dftb .row.cursor{outline:1px solid #6a9ad8;outline-offset:-1px}
.dftb .row button.related-open{border:none;background:none;padding:0 2px;font-size:13px}
.dftb .related{display:flex;gap:6px;align-items:center;flex-wrap:wrap;background:#2a3a2f;border:1px solid #4a7a5a;border-radius:6px;padding:5px 8px;max-height:120px;overflow:auto}
.dftb .related .chip{display:inline-flex;border:1px solid #4a7a5a;border-radius:12px;overflow:hidden}.dftb .related .chip.on{border-color:#8fc0ff}
.dftb .related .chip button{border:none;border-radius:0;padding:1px 7px;font-size:12px;background:#24302a}.dftb .related .chip button.add{color:#bfe8bf;border-left:1px solid #4a7a5a}.dftb [hidden]{display:none!important}
.dftb .row button.pick{border:none;background:none;font-size:16px;color:#888;padding:0 2px}.dftb .row button.pick.on{color:#8fc0ff}.dftb .row.picked{background:#2a3444}
.dftb .basket{display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:#2a3444;border:1px solid #4a6a9a;border-radius:6px;padding:5px 8px}
.dftb .basket .tags{flex:1;min-width:0;color:#cfe0ff;font-size:13px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.dftb .basket button.add{border-color:#4a7a4a;color:#bfe8bf}.dftb .basket button.neg{border-color:#7a4a4a;color:#f0c0c0}
`;
const TYPES = [["", "All"], ["general", "General"], ["character", "👤 Characters"], ["copyright", "©️ Series"], ["artist", "🎨 Artists"], ["meta", "⚙️ Meta"], ["favorites", "★ Favorites"]];
const KIND_NAMES = { general: "general", character: "👤 character", copyright: "©️ series", artist: "🎨 artist", meta: "⚙️ meta" };
const PAGE = 100;

// The tags a prompt has, in lower case as written (spaces, escaped parentheses), a weight like (smile:1.2) left aside.
export function promptTags(text) {
  return new Set(String(text ?? "").split(/[,\n]/).map((part) => {
    const weighted = /^\((.+):[\d.]+\)$/.exec(part.trim());
    return (weighted ? weighted[1] : part).trim().toLowerCase();
  }).filter(Boolean));
}
const tagIn = (tags, tag) => tags.has(tagText(tag).toLowerCase()) || tags.has(tag.toLowerCase());

const TAG_KEYS = [["/", "Jump to the search"], ["↑ / ↓", "Pick a tag (from the search too)"], ["Enter", "Put it where the cursor was in the prompts"],
  ["Shift+Enter", "Put it in the negative prompt"], ["Ctrl+Enter", "Put it in the basket (or take it out)"], ["Esc", "Close"], ["?", "These keys"]];

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
  // The basket: tags picked (☐ on a row) while searching and switching types, then put into a prompt all at once.
  const picked = new Map(), basket = element("div", { class: "basket", hidden: "" });
  function drawBasket() {
    basket.hidden = !picked.size;
    const texts = [...picked.keys()].map(tagText);
    basket.replaceChildren(element("b", { class: "count" }, `${picked.size} picked`), element("span", { class: "tags", title: texts.join(", ") }, texts.join(", ")),
      element("button", { class: "add", title: "Put them all where the cursor was in the prompts", onclick: () => addPicked() }, "+ Add all"),
      ...(fieldsOf(node)?.includes("negative") ? [element("button", { class: "neg", title: "Put them all in the negative prompt", onclick: () => addPicked("negative") }, "− Neg all")] : []),
      element("button", { class: "clear", title: "Empty the basket", onclick: () => { picked.clear(); drawBasket(); draw(true); } }, "Clear"));
  }
  function addPicked(field) {
    const target = field ?? cursorField(node, undefined), there = fieldTags(target);
    const fresh = [...picked.keys()].filter((tag) => !tagIn(there, tag)), texts = fresh.map(tagText), skipped = picked.size - fresh.length;
    const where = texts.length ? keepFocus(() => insertIntoNode(node, texts.join(", "), field)) : target;
    picked.clear();
    drawBasket();
    draw(true);
    say(`Added ${texts.length} tag${texts.length === 1 ? "" : "s"} to the ${where} prompt.${skipped ? ` ${skipped} ${skipped === 1 ? "was" : "were"} already there.` : ""}`);
  }
  // 🔗 Related: the tags Danbooru finds most often with a tag, as chips (click: into the basket; +: into the prompt).
  const related = element("div", { class: "related", hidden: "" });
  async function showRelated(tag) {
    related.hidden = false;
    related.replaceChildren(element("span", { class: "muted" }, `🔗 Asking Danbooru about ${tag.tag}…`));
    let result;
    try {
      result = await request(`/diceforge/tags/related?tag=${encodeURIComponent(tag.tag)}`);
    } catch (error) {
      related.replaceChildren(element("span", { class: "muted" }, error.message), closeRelated());
      return;
    }
    const chips = result.related.map((item) => {
      const entry = { ...item, aliases: [] }, on = picked.has(item.tag);
      return element("span", { class: "chip" + (on ? " on" : ""), "data-tag": item.tag },
        element("button", { class: "pick-chip", title: `${KIND_NAMES[item.type] ?? item.type}${item.count ? `, ${item.count.toLocaleString()} posts` : ""}: click for the basket`,
          onclick: () => { togglePick(entry); background(showRelated(tag)); } }, `${on ? "☑" : "☐"} ${item.tag}`),
        element("button", { class: "add", title: "Put it where the cursor was in the prompts", onclick: () => add(entry) }, "+"));
    });
    related.replaceChildren(element("b", {}, `🔗 Often with ${tag.tag}:`), ...(chips.length ? chips : [element("span", { class: "muted" }, " none known.")]), closeRelated());
  }
  const closeRelated = () => element("button", { class: "close-related", title: "Close", onclick: () => { related.hidden = true; } }, "✕");
  function togglePick(tag) {
    if (picked.has(tag.tag)) picked.delete(tag.tag);
    else picked.set(tag.tag, tag);
    drawBasket();
    draw(true);
  }
  const back = element("div", { class: "dftb-back" });
  const onKey = (event) => {
    if (asking()) return;
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
    } else if (!keysOnQuestion(event, "Tag Browser", TAG_KEYS) && !slashToSearch(event, search)) listKeys(event);
  };
  // The keyboard (from the search box too): ↑ ↓ pick a tag, Enter puts it where the cursor was, Shift+Enter in the negative prompt, Ctrl+Enter
  // puts it in the basket (or takes it out).
  let cursorTag = null;
  function listKeys(event) {
    if (typingIn(event) && event.target !== search) return;
    const tag = () => tags.find((item) => item.tag === cursorTag);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") cursorTag = moveCursor([...list.querySelectorAll(".row")], event.key === "ArrowDown" ? 1 : -1)?.dataset.tag ?? null;
    else if (event.key === "Enter" && tag()) {
      if (event.ctrlKey || event.metaKey) togglePick(tag());
      else add(tag(), event.shiftKey ? "negative" : undefined);
    } else return;
    event.preventDefault();
    event.stopPropagation();
  }
  function close() {
    remember("tags", { search: search.value, kind, sort: sort.value, scroll: list.scrollTop });
    stopSize();
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
  // What the node's prompts have (✓ on a row): + Add doesn't put a tag twice in the same prompt.
  // Inserting moves the focus to the prompt field: it comes back here, so the browser's keys go on working.
  const keepFocus = (insert) => {
    const focused = document.activeElement, result = insert();
    if (focused && back.contains(focused)) focused.focus({ preventScroll: true });
    return result;
  };
  const fieldTags = (field) => promptTags(node.widgets?.find((widget) => widget.name === field)?.value);
  const inPrompts = (tag) => (fieldsOf(node) ?? []).filter((field) => tagIn(fieldTags(field), tag.tag));
  function add(tag, field) {
    const target = field && fieldsOf(node)?.includes(field) ? field : cursorField(node, undefined);
    if (tagIn(fieldTags(target), tag.tag)) return say(`${tagText(tag.tag)} is already in the ${target} prompt.`);
    const where = keepFocus(() => insertIntoNode(node, tagText(tag.tag), field));
    draw(true);
    say(`Added ${tagText(tag.tag)} to the ${where} prompt.`);
  }
  function row(tag) {
    const on = picked.has(tag.tag), there = inPrompts(tag);
    return element("div", { class: "row" + (on ? " picked" : "") + (tag.tag === cursorTag ? " cursor" : ""), "data-tag": tag.tag },
      element("button", { class: "pick" + (on ? " on" : ""), title: on ? "In the basket: click to take it out" : "Pick it for the basket (several tags at once)",
        onclick: () => togglePick(tag) }, on ? "☑" : "☐"),
      element("button", { class: "fav" + (tag.favorite ? " on" : ""), title: tag.favorite ? "A favorite: click to remove the star" : "Add to favorites",
        onclick: () => background(setFavorite(tag, !tag.favorite)) }, tag.favorite ? "★" : "☆"),
      element("span", { class: "name", title: tag.aliases.length ? `Also: ${tag.aliases.join(", ")}` : "" }, element("b", {}, tag.tag),
        ...(tag.aliases.length ? [element("span", { class: "aliases" }, tag.aliases.slice(0, 3).join(", "))] : [])),
      ...(there.length ? [element("span", { class: "has", title: `Already in the ${there.join(" and ")} prompt` }, "✓")] : []),
      element("span", { class: "kind" }, KIND_NAMES[tag.type] ?? tag.type),
      element("span", { class: "count", title: `${tag.count.toLocaleString()} posts` }, compact(tag.count)),
      element("button", { class: "add", title: "Put it where the cursor was in the prompts", onclick: () => add(tag) }, "+ Add"),
      ...(fieldsOf(node)?.includes("negative") ? [element("button", { class: "neg", title: "Put it in the negative prompt", onclick: () => add(tag, "negative") }, "− Neg")] : []),
      ...(tag.site === "e621" ? [] : [element("button", { class: "related-open", title: "Related: the tags Danbooru finds most often with it", onclick: () => background(showRelated(tag)) }, "🔗")]),
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
  const heading = element("h2", {}, "Tag Browser"), dialog = element("div", { class: "dftb" });
  const stopSize = keepSize(dialog, "tags", heading);
  back.append(dialog);
  dialog.append(
    heading,
    element("div", { class: "top" }, search, sort, keysButton("Tag Browser", TAG_KEYS), element("button", { onclick: close }, "Close")),
    types, basket, related, list, status);
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
