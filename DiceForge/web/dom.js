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
