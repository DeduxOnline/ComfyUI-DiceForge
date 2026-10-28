import { app } from "../../scripts/app.js";
import { addStyleOnce, asking, background, element, fitToContent } from "./dom.js";
import { toast } from "./comfy.js";
import { blurOn } from "./media.js";
import { fitNodeHeight } from "./node_size.js";
import { keepSize } from "./window_memory.js";

// Danbooru Tag Enhancer keeps one row under its inputs about the last run (its posts and the tags they added), so the node's height never
// changes with a run. The run itself opens in a window, from that row or the node's menu: the Danbooru or e621 posts (their pictures; a click
// opens one), the added tags (Copy tags), the search that found them, and Keep these posts, which switches mode to fixed. After a random run the
// node's post_ids and wildcard_seed get that run's posts and seed, so fixed takes them again (as a seed's fixed). Kept in the node's properties,
// so it is still there after a reload and travels with the workflow.
const NODE_TYPE = "DiceForgeDanbooruEnhancer";
const RATINGS = { g: "general", s: "sensitive", q: "questionable", e: "explicit" }; // Danbooru's, for results saved without rating_name.
const ratingName = (post) => post.rating_name || RATINGS[post.rating] || "";
const SITES = { e621: "e621 ", safebooru: "Safebooru " }; // Named before the posts (Danbooru is the default).
const EMPTY = "Run the workflow to see the Danbooru posts it takes and the tags they add here.";
const STYLE = `
.dfdb{font:12px system-ui,sans-serif;color:#ccc;display:flex;flex-direction:column;box-sizing:border-box;padding:2px 0}
.dfdb .last-run,.dfdb .empty{width:100%;box-sizing:border-box;border:1px dashed #4a4a4a;border-radius:6px;padding:5px 8px;font:inherit;line-height:16px;text-align:left;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.dfdb .last-run{background:#232323;color:#ddd;cursor:pointer}.dfdb .last-run:hover{background:#2c2c2c}.dfdb .empty{border-color:transparent;color:#777;font-style:italic}
.dfdbw-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dfdbw{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(760px,95vw);height:min(620px,92vh);display:flex;flex-direction:column;gap:8px;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dfdbw h2{margin:0;font-size:20px;color:#fff}.dfdbw .top{display:flex;gap:8px;align-items:center}.dfdbw .top .muted{flex:1}.dfdbw .muted{color:#999;font-size:13px}
.dfdbw button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:3px 9px;cursor:pointer;font:inherit;font-size:13px}.dfdbw button:hover{background:#2c2c2c}
.dfdbw button.keep{background:#1e88e5;border-color:#1e88e5;color:#fff}.dfdbw button:disabled{opacity:.5;cursor:default}
.dfdbw .body{flex:1;overflow:auto;display:flex;flex-direction:column;gap:8px;padding-right:4px}
.dfdbw .thumbs{display:flex;gap:6px;flex-wrap:wrap}
.dfdbw .thumb{display:block;height:180px;max-width:100%;border-radius:6px;overflow:hidden;border:1px solid #444;background:#222;color:#9cc8ff;text-decoration:none}
.dfdbw .thumb img{height:100%;max-width:100%;object-fit:cover;display:block}.dfdbw .thumb img.blur{filter:blur(14px)}
.dfdbw .thumb.plain{height:auto;padding:3px 7px}
.dfdbw .added{color:#9c9;white-space:pre-wrap;word-break:break-word;border:1px solid transparent;border-radius:5px;padding:2px 4px}
.dfdbw .added.copied{border-color:#6a9a6a}.dfdbw .tags,.dfdbw .search{color:#999;font-size:13px;word-break:break-word}
.dfdbw .actions{display:flex;gap:8px;flex-wrap:wrap}.dfdbw .empty{color:#999;padding:16px}
`;

const postsName = (last) => {
  const posts = last.posts;
  const rating = ratingName(posts[0]) ? " (" + ratingName(posts[0]) + ")" : "";
  return (SITES[last.site] || "") + (posts.length === 1 ? "post #" + posts[0].id + rating : posts.length + " posts");
};
// The node's row about a run: its posts, how many tags they added, and fixed.
export function summary(last) {
  const count = (last.added || "").split(",").map((tag) => tag.trim()).filter(Boolean).length;
  const added = count ? "+" + count + (count === 1 ? " tag" : " tags") : "no tags added";
  return `Last run: ${postsName(last)}, ${added}${last.mode === "fixed" ? " · fixed" : ""}`;
}

// A post's picture, linked to the post; blurred (until clicked) when it isn't safe (Danbooru's general, e621's safe), unless Blur NSFW is off
// (DiceForge → Browsers).
function thumb(post) {
  const title = `Post #${post.id}${ratingName(post) ? ` (${ratingName(post)})` : ""}: open it`;
  const plain = () => element("a", { class: "thumb plain", href: post.url, target: "_blank", rel: "noopener", title }, `↗ #${post.id}`);
  if (!post.preview) return plain();
  const img = element("img", { src: post.preview, referrerpolicy: "no-referrer", loading: "lazy" });
  const link = element("a", { class: "thumb", href: post.url, target: "_blank", rel: "noopener", title }, img);
  img.addEventListener("error", () => link.replaceWith(plain())); // Danbooru's pictures out of reach: the link to the post.
  if (blurOn() && !(post.safe ?? post.rating === "g")) {
    img.classList.add("blur");
    link.addEventListener("click", (event) => {
      if (!img.classList.contains("blur")) return;
      event.preventDefault(); // The first click only reveals.
      img.classList.remove("blur");
    });
  }
  return link;
}
// A widget's new value, as typed (its callback too: the canvas and Nodes 2.0 show it).
function setWidget(node, name, value) {
  const widget = node.widgets?.find((item) => item.name === name);
  if (!widget || widget.value === value) return;
  widget.value = value;
  widget.callback?.(value);
}
const widgetValue = (node, name) => node.widgets?.find((item) => item.name === name)?.value;
// The run's posts and wildcards again on every run: post_ids and wildcard_seed of that run, with mode on fixed.
function keepPosts(node, last) {
  setWidget(node, "post_ids", last.post_ids);
  if (Number.isInteger(last.wildcard_seed)) setWidget(node, "wildcard_seed", last.wildcard_seed);
  setWidget(node, "mode", "fixed");
  node.setDirtyCanvas?.(true, true);
}
const kept = (node, last) => widgetValue(node, "mode") === "fixed" && widgetValue(node, "post_ids") === last.post_ids;
function copyAdded(last, done) {
  if (!navigator.clipboard) return toast("warn", "Can't copy here", "The browser allows copying only on https or localhost.");
  background(navigator.clipboard.writeText(last.added)); // A refused copy (no permission) is logged, not thrown.
  done();
}

export function openPosts(node) {
  addStyleOnce("dfdb-style", STYLE);
  const body = element("div", { class: "body" });
  const info = element("span", { class: "muted" });
  const heading = element("h2", {}, `Danbooru posts · ${node.title || "Danbooru Tag Enhancer"}`);
  const dialog = element("div", { class: "dfdbw" }, heading, element("div", { class: "top" }, info, element("button", { onclick: () => close() }, "Close")), body);
  const back = element("div", { class: "dfdbw-back" }, dialog);
  const onKey = (event) => { if (asking()) return; if (event.key === "Escape") { event.stopPropagation(); close(); } };
  let shown;
  const timer = setInterval(() => { if (node.properties?.dice_forge_danbooru !== shown) draw(); }, 400); // A run while it is open shows up.
  const stopSize = keepSize(dialog, "danbooru", heading);
  function close() {
    clearInterval(timer);
    stopSize();
    back.remove();
    document.removeEventListener("keydown", onKey, true);
  }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  function draw() {
    const last = shown = node.properties?.dice_forge_danbooru;
    const posts = last?.posts ?? [];
    if (!posts.length) {
      info.textContent = "";
      body.replaceChildren(element("div", { class: "empty" }, EMPTY));
      return;
    }
    info.textContent = `${postsName(last)} · ${last.mode || "random"}`;
    const added = element("div", { class: "added" }, last.added ? `+ ${last.added}` : "Nothing to add: the posts have no other tags.");
    const copy = element("button", { class: "copy", title: "Copy the added tags",
      onclick: () => copyAdded(last, () => { added.classList.add("copied"); setTimeout(() => added.classList.remove("copied"), 600); }) }, "Copy tags");
    copy.disabled = !last.added;
    const keep = element("button", { class: "keep", title: "Mode fixed with these posts and wildcards: every run takes them again",
      onclick: () => { keepPosts(node, last); keep.disabled = true; keep.textContent = "Kept (fixed)"; } }, kept(node, last) ? "Kept (fixed)" : "Keep these posts (fixed)");
    keep.disabled = kept(node, last);
    const typed = widgetValue(node, "tags");
    body.replaceChildren(
      element("div", { class: "thumbs" }, ...posts.map(thumb)),
      added,
      ...(last.tags && last.tags !== typed?.trim() ? [element("div", { class: "tags" }, `Tags: ${last.tags}`)] : []), // Wildcards filled in.
      element("div", { class: "search" }, last.mode === "fixed" ? `Fixed: post${posts.length > 1 ? "s" : ""} ${last.post_ids}` : `Searched: ${last.search || "any post"}`),
      element("div", { class: "actions" }, copy, keep));
  }
  document.body.append(back);
  draw();
}

app.registerExtension({
  name: "DiceForge.DanbooruPreview",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    addStyleOnce("dfdb-style", STYLE);
    const panel = element("div", { class: "dfdb" });
    fitToContent(node.addDOMWidget("danbooru_preview", "diceforge_danbooru_preview", panel, { serialize: false }), panel);
    let shownFrom; // The result the row shows (undefined: not drawn yet).
    function render() {
      const last = shownFrom = node.properties?.dice_forge_danbooru;
      panel.replaceChildren(last?.posts?.length
        ? element("button", { class: "last-run", title: "Open the posts and tags of the last run", onclick: () => openPosts(node) }, summary(last))
        : element("div", { class: "empty", title: EMPTY }, EMPTY)); // One line as the button, so a run doesn't change the node's height.
      fitNodeHeight(node);
    }
    const onExecuted = node.onExecuted;
    node.onExecuted = function (output) {
      const result = output?.dice_forge_danbooru?.[0];
      if (result) {
        node.properties ??= {};
        node.properties.dice_forge_danbooru = result;
        if (result.mode !== "fixed") { // This run's posts and wildcards: fixed mode takes them again.
          setWidget(node, "post_ids", result.post_ids);
          setWidget(node, "wildcard_seed", result.wildcard_seed);
        }
        render();
      }
      return onExecuted?.apply(this, arguments);
    };
    // Drawn again when the saved result arrives (a loaded workflow gives the node its properties after this extension ran, in the classic canvas).
    const timer = setInterval(() => { if (node.properties?.dice_forge_danbooru !== shownFrom) render(); }, 500);
    const onRemoved = node.onRemoved;
    node.onRemoved = function () {
      clearInterval(timer);
      return onRemoved?.apply(this, arguments);
    };
    render();
  },
  getNodeMenuItems(node) {
    if (node.comfyClass !== NODE_TYPE) return [];
    const last = node.properties?.dice_forge_danbooru;
    return [
      { content: "🏷 Danbooru posts of the last run…", callback: () => openPosts(node) },
      ...(last?.added ? [{ content: "📋 Copy the added tags", callback: () => copyAdded(last, () => toast("success", "Copied the added tags", last.added)) }] : []),
    ];
  },
});
