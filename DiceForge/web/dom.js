// Shared helpers of the DiceForge frontend extensions: building elements, adding a stylesheet once, and starting async steps in the background.
export function element(tag, attributes = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === "class") node.className = value;
    else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
    else node.setAttribute(key, value);
  }
  for (const child of children) node.append(child instanceof Node ? child : document.createTextNode(String(child ?? "")));
  return node;
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
