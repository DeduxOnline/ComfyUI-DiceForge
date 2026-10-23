// Shared helpers of the DiceForge frontend extensions: building elements, adding a stylesheet once, and starting async steps in the background.
export function element(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, key === "href" || key === "src" ? safeURL(value) : value);
  }
  for (const child of children) node.append(child instanceof Node ? child : document.createTextNode(String(child ?? "")));
  return node;
}
// Links and pictures from outside data (Civitai's and Danbooru's answers, the previews a workflow carries in its node properties) are web
// addresses or this server's own: any other scheme (javascript:, data:, file:) becomes empty, so a link from a shared workflow can't run a script.
export function safeURL(url) {
  const text = String(url ?? "");
  try {
    return ["http:", "https:", "blob:"].includes(new URL(text, location.href).protocol) ? text : "";
  } catch {
    return "";
  }
}
// Opens a link from outside data in a new tab (only a web address, see safeURL).
export function openLink(url) {
  const safe = safeURL(url);
  if (safe) window.open(safe, "_blank", "noopener");
}
// A stylesheet added to the page once, by its id.
export function addStyleOnce(id, css) {
  if (document.getElementById(id)) return;
  const style = document.createElement("style");
  style.id = id;
  style.textContent = css;
  document.head.append(style);
}
// Runs an async step without awaiting it; a failure (the server not answering...) is logged instead of being an unhandled rejection. Returns nothing.
export const background = (step) => { Promise.resolve(step).catch((error) => console.error("[DiceForge]", error)); };
// Questions in ComfyUI's own dialogs: the browser's confirm() and prompt() don't show everywhere (ComfyUI Desktop has no prompt(), and some
// embedded browsers answer them at once, unseen); they stay the fallback on a ComfyUI without its dialogs. The dialog is raised over the DiceForge
// windows (z-index 10000), and while it is open they leave the keys to it (asking()): Escape closes it, not the window under it.
let questions = 0;
export const asking = () => questions > 0;
const DIALOGS = '[role="dialog"], [role="alertdialog"]';
function raiseNewDialog(before) {
  let frames = 0;
  const look = () => {
    const dialog = [...document.querySelectorAll(DIALOGS)].find((node) => !before.has(node));
    if (!dialog) {
      if (++frames < 120) requestAnimationFrame(look); // Shown a frame or a few after it is asked for.
      return;
    }
    dialog.style.setProperty("z-index", "10002", "important");
    const overlay = dialog.previousElementSibling;
    if (overlay && !overlay.matches(DIALOGS) && getComputedStyle(overlay).position === "fixed") overlay.style.setProperty("z-index", "10001", "important");
  };
  requestAnimationFrame(look);
}
async function ask(kind, options, fallback) {
  const dialogs = window.app?.extensionManager?.dialog;
  if (typeof dialogs?.[kind] !== "function") return fallback();
  const before = new Set(document.querySelectorAll(DIALOGS));
  questions++;
  try {
    const answer = dialogs[kind](options);
    raiseNewDialog(before);
    return await answer;
  } finally {
    questions--;
  }
}
// true when confirmed (type "delete" makes its button a delete button).
export async function askConfirm(message, type = "default") {
  return (await ask("confirm", { title: "DiceForge", message, type }, () => window.confirm(message))) === true;
}
// The text typed, or null when cancelled.
export async function askText(message, defaultValue = "") {
  const answer = await ask("prompt", { title: "DiceForge", message, defaultValue }, () => window.prompt(message, defaultValue));
  return typeof answer === "string" ? answer : null;
}
// The height of a panel's content: from its first shown child's top to its last one's bottom, with its padding and border. Not its scrollHeight:
// that is at least the height the node gave the panel, so a panel asking for it keeps every height it was once given (a node made taller, a
// workflow saved tall), an empty area under its content that no fitting takes back. A panel without its width yet (just added to a node) has
// its text broken at every word: it asks for nothing until it has one, or the node would keep that height.
export function contentHeight(panel) {
  const style = getComputedStyle(panel);
  const frame = ["paddingTop", "paddingBottom", "borderTopWidth", "borderBottomWidth"].reduce((sum, key) => sum + (Number.parseFloat(style[key]) || 0), 0);
  const shown = [...panel.children].filter((child) => child.offsetParent !== null);
  if (!shown.length || !panel.offsetWidth) return frame;
  return Math.max(...shown.map((child) => child.offsetTop + child.offsetHeight)) - Math.min(...shown.map((child) => child.offsetTop)) + frame;
}
// A panel's DOM widget as tall as the panel's content (up to `most`), no more and no less, in both designs: a taller node gives the extra height
// to its text fields, not to an empty area under the panel. A DOM widget with a layout size takes a share of the extra height (Nodes 2.0 gives
// it a growing row), one with its own computeSize does not. The classic canvas puts the panel a margin below the widget's top and makes it
// 2 × margin - 4 shorter than computeSize says, so the widget asks for that too.
export function fitToContent(widget, panel, most = Infinity) {
  // Its parts keep their own height when the panel is shorter (new content, before the node grows for it): squeezed, they would be measured so.
  addStyleOnce("df-fit-style", ".df-fit>*{flex-shrink:0}");
  panel.classList.add("df-fit");
  widget.computeLayoutSize = undefined;
  widget.computeSize = (width) => [width ?? 0, Math.min(contentHeight(panel), most) + 2 * (widget.margin ?? 10) - 4];
  return widget;
}
