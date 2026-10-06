// What a DiceForge window showed when it was closed (its search, filters, the open file, where it was scrolled), so it opens there again instead
// of from the start: kept per window in this browser, also after a reload. Without storage (private mode) the windows open as new.
const PREFIX = "diceforge.window.";

export function recall(name) {
  try {
    const state = JSON.parse(localStorage.getItem(PREFIX + name));
    return state && typeof state === "object" && !Array.isArray(state) ? state : {};
  } catch {
    return {};
  }
}

export function remember(name, state) {
  try { localStorage.setItem(PREFIX + name, JSON.stringify(state)); } catch { /* No storage, or too big (a long unsaved text): opens as new. */ }
}

// A remembered scroll position, put back once the content is drawn (the next frame: drawn content has its height then).
export function scrollBack(element, top) {
  if (!(top > 0)) return;
  element.scrollTop = top;
  requestAnimationFrame(() => { element.scrollTop = top; });
}

// A window's size: dragged by its bottom-right corner, kept for the next time (per window, in this browser); a double-click on its title puts
// the default size back. Never larger than the screen.
export function keepSize(dialog, name, title) {
  const key = `size.${name}`;
  Object.assign(dialog.style, { resize: "both", overflow: "hidden", maxWidth: "98vw", maxHeight: "96vh", minWidth: "420px", minHeight: "320px" });
  const size = recall(key);
  if (size.width > 0 && size.height > 0) Object.assign(dialog.style, { width: `${size.width}px`, height: `${size.height}px` });
  let ready = false; // The first report is the size it opened with, not a drag.
  const observer = new ResizeObserver(() => {
    if (!ready) {
      ready = true;
      return;
    }
    if (dialog.isConnected && dialog.style.width.endsWith("px")) remember(key, { width: dialog.offsetWidth, height: dialog.offsetHeight });
  });
  observer.observe(dialog);
  if (title) {
    title.title = "Drag the bottom-right corner to resize the window; double-click here for its default size";
    title.addEventListener("dblclick", () => {
      dialog.style.width = dialog.style.height = "";
      remember(key, {});
    });
  }
  return () => observer.disconnect();
}
