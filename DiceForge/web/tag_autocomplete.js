import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { background } from "./dom.js";
import { compact } from "./civitai_meta.js";
import { addCompletionSource, isPromptNode } from "./wildcards.js";

// Danbooru and e621 tag autocomplete in the prompt fields (tag_autocomplete.py): while a word is typed, the most used tags that start with it (or an
// alias of them), with how often each is used. Accepting one puts it in as the models learned it: spaces for underscores (except in emoticons like
// ^_^), escaped parentheses, and a comma after it. The tag lists are downloaded from the node's menu (🏷 Tag autocomplete) or put in
// ComfyUI/user/DiceForge/tags; a setting turns the autocomplete off.
const SETTING = "DiceForge.TagAutocomplete";
const TYPE_MARKS = { general: "", artist: "🎨 ", copyright: "©️ ", character: "👤 ", meta: "⚙️ " };
const enabled = () => app.extensionManager?.setting?.get?.(SETTING) !== false;
let ready = null, checked = 0; // Whether a list is there (null: not asked yet); asked again after a while when there was none.

export function tagText(tag) {
  const spaced = /[a-z]{2}/i.test(tag) && tag.length > 3 ? tag.replace(/_/g, " ") : tag; // ^_^ and >_< keep their underscores.
  return spaced.replace(/([()])/g, "\\$1");
}
// The word being typed: after the last comma, line break, brace, bar or parenthesis, without the spaces before it. null when it isn't a tag being
// typed (too short, a number, a wildcard, a variable or a LoRA tag).
export function typedWord(before) {
  const start = Math.max(...[",", "\n", "{", "}", "|", "(", ")", "[", "]"].map((separator) => before.lastIndexOf(separator))) + 1;
  const word = before.slice(start).replace(/^\s+/, "");
  if (word.length < 2 || !/\p{L}/u.test(word) || /[<>:$_]{2}|[<$]/.test(word)) return null; // 1girl is a tag; 1.2 is not.
  return { word, start: before.length - word.length };
}
async function search(word) {
  const response = await api.fetchApi(`/diceforge/tags?${new URLSearchParams({ q: word, limit: "12" })}`);
  if (!response.ok) return [];
  const body = await response.json();
  ready = body.ready;
  checked = Date.now();
  return body.tags;
}
addCompletionSource((before) => {
  if (!enabled() || (ready === false && Date.now() - checked < 30000)) return null;
  const typed = typedWord(before);
  if (!typed) return null;
  const items = search(typed.word).then((tags) => tags.map((tag) => ({
    label: `${TYPE_MARKS[tag.type] ?? ""}${tag.alias ? `${tag.alias} → ` : ""}${tag.tag}`, hint: compact(tag.count), insert: `${tagText(tag.tag)}, ` })));
  return { start: typed.start, items };
});

// The lists in the node's menu: download (or download again) each one.
let lists = [];
async function loadLists() {
  try { lists = (await (await api.fetchApi("/diceforge/tags/lists")).json()).lists; } catch { /* No answer: the menu offers what it had. */ }
}
function toast(severity, summary, detail) {
  const toaster = app.extensionManager?.toast;
  if (toaster?.add) toaster.add({ severity, summary, detail, life: 5000 });
  else if (severity === "error") alert(`${summary}: ${detail}`);
}
async function download(list) {
  toast("info", "Tag autocomplete", `Downloading the ${list.name} tags…`);
  const response = await api.fetchApi("/diceforge/tags/download", { method: "POST", body: JSON.stringify({ list: list.name }) });
  if (!response.ok) {
    toast("error", "Tag autocomplete", await response.text());
    return;
  }
  const { tags } = await response.json();
  ready = true;
  toast("success", "Tag autocomplete", `${tags.toLocaleString()} ${list.name} tags: type a word in a prompt field.`);
  await loadLists();
}

app.registerExtension({
  name: "DiceForge.TagAutocomplete",
  settings: [{
    id: SETTING,
    category: ["DiceForge", "Prompts", "Tags"],
    name: "Suggest Danbooru / e621 tags in CLIP Dual Text Encode",
    tooltip: "While a word is typed in a prompt field, the most used tags that start with it. The tag lists are downloaded from the node's menu (🏷 Tag autocomplete).",
    type: "boolean",
    defaultValue: true,
  }],
  setup() {
    background(loadLists());
  },
  getNodeMenuItems(node) {
    if (!isPromptNode(node)) return [];
    const options = lists.map((list) => ({ content: `${list.here ? "✓ Download again" : "⬇ Download"}: ${list.title}`, callback: () => background(download(list)) }));
    return [{ content: "🏷 Tag autocomplete", has_submenu: true, submenu: { options } }];
  },
});
