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
