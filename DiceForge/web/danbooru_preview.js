import { app } from "../../scripts/app.js";
import { addStyleOnce, background, element } from "./dom.js";
import { blurOn } from "./media.js";
import { fitNodeHeight } from "./node_size.js";

// Danbooru Tag Enhancer shows, under its inputs, what the last run took: the Danbooru or e621 posts (their pictures; ↗ opens one), the added tags (click to copy)
// and the search that found them. After a random run the node's post_ids and wildcard_seed get that run's posts and seed, so switching mode to
// fixed keeps it (as a seed's fixed). Kept in the node's properties, so it is still there after a reload and travels with the workflow.
const NODE_TYPE = "DiceForgeDanbooruEnhancer";
const RATINGS = { g: "general", s: "sensitive", q: "questionable", e: "explicit" }; // Danbooru's, for results saved without rating_name.
const ratingName = (post) => post.rating_name || RATINGS[post.rating] || "";
const SITES = { e621: "e621 ", safebooru: "Safebooru " }; // Named in the head (Danbooru is the default).
const STYLE = `
.dfdb{font:12px system-ui,sans-serif;color:#ccc;display:flex;flex-direction:column;gap:4px;box-sizing:border-box;padding:2px 0}
.dfdb .head{color:#888}.dfdb .thumbs{display:flex;gap:4px;flex-wrap:wrap}
.dfdb .thumb{display:block;height:120px;max-width:100%;border-radius:5px;overflow:hidden;border:1px solid #444;background:#222;color:#9cc8ff;text-decoration:none}
.dfdb .thumb img{height:100%;max-width:100%;object-fit:cover;display:block}.dfdb .thumb img.blur{filter:blur(14px)}
.dfdb .thumb.plain{height:auto;padding:3px 7px}
.dfdb .added{color:#9c9;white-space:pre-wrap;word-break:break-word;cursor:copy;border:1px solid transparent;border-radius:5px;padding:2px 4px}
.dfdb .added.copied{border-color:#6a9a6a}.dfdb .tags,.dfdb .search{color:#888;font-size:11px;word-break:break-word}.dfdb .empty{color:#777;font-style:italic;padding:6px}
`;

// A post's picture, linked to the post; blurred (until clicked) when it isn't safe (Danbooru's general, e621's safe), unless Blur NSFW is off
// (DiceForge → Browsers).
function thumb(post, onLoad) {
  const title = `Post #${post.id}${ratingName(post) ? ` (${ratingName(post)})` : ""}: open it`;
  const plain = () => element("a", { class: "thumb plain", href: post.url, target: "_blank", rel: "noopener", title }, `↗ #${post.id}`);
  if (!post.preview) return plain();
  const img = element("img", { src: post.preview, referrerpolicy: "no-referrer", loading: "lazy" });
  img.addEventListener("load", onLoad);
  const link = element("a", { class: "thumb", href: post.url, target: "_blank", rel: "noopener", title }, img);
  img.addEventListener("error", () => { link.replaceWith(plain()); onLoad(); }); // Danbooru's pictures out of reach: the link to the post.
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

app.registerExtension({
  name: "DiceForge.DanbooruPreview",
  nodeCreated(node) {
    if (node.comfyClass !== NODE_TYPE) return;
    addStyleOnce("dfdb-style", STYLE);
    const panel = element("div", { class: "dfdb" });
    node.addDOMWidget("danbooru_preview", "diceforge_danbooru_preview", panel, { serialize: false, getMinHeight: () => panel.scrollHeight + 4 });
    let shownFrom; // The result the panel shows (undefined: not drawn yet).
    function render() {
      const last = node.properties?.dice_forge_danbooru;
      shownFrom = last;
      const posts = last?.posts || (last?.id ? [{ id: last.id, url: last.url, rating: last.rating }] : []); // Also a result saved before posts.
      if (!posts.length) {
        panel.replaceChildren(element("div", { class: "empty" }, "Run the workflow to see the Danbooru posts it takes and the tags they add here."));
      } else {
        const one = `${SITES[last.site] || ""}${posts.length === 1 ? `post #${posts[0].id}${ratingName(posts[0]) ? ` (${ratingName(posts[0])})` : ""}` : `${posts.length} posts`}`;
        const added = element("div", { class: "added", title: "Click to copy the added tags" }, last.added ? `+ ${last.added}` : "Nothing to add: the posts have no other tags.");
        added.addEventListener("click", () => {
          if (!last.added || window.getSelection()?.toString()) return; // Selecting a part to copy it yourself.
          background(navigator.clipboard?.writeText(last.added)); // A refused copy (no permission) is logged, not thrown.
          added.classList.add("copied");
          setTimeout(() => added.classList.remove("copied"), 600);
        });
        const typed = node.widgets?.find((item) => item.name === "tags")?.value;
        panel.replaceChildren(
          element("div", { class: "head" }, `Last run · ${one}${last.mode === "fixed" ? " · fixed" : ""}`),
          element("div", { class: "thumbs" }, ...posts.map((post) => thumb(post, () => fitNodeHeight(node)))),
          added,
          ...(last.tags && last.tags !== typed?.trim() ? [element("div", { class: "tags" }, `Tags: ${last.tags}`)] : []), // Wildcards filled in.
          element("div", { class: "search" }, last.mode === "fixed" ? `Fixed: post${posts.length > 1 ? "s" : ""} ${last.post_ids}` : `Searched: ${last.search || "any post"}`));
      }
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
});
