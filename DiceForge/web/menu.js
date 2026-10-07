import { addStyleOnce, background, element } from "./dom.js";

// The right-click menu of the browsers' rows and cards (and their ⋯ buttons): items are [label, action, title?] or "-" for a line. It closes on
// a pick, on a click elsewhere, or with Escape (the window's own Escape asks menuOpen() first and calls closeMenu()).
const STYLE = `
.df-menu{position:fixed;z-index:10002;background:#262626;border:1px solid #555;border-radius:6px;box-shadow:0 6px 20px #000a;padding:4px;display:flex;flex-direction:column;min-width:210px;font:13px system-ui,sans-serif}
.df-menu button{background:none;border:none;color:#ddd;text-align:left;padding:5px 10px;border-radius:4px;cursor:pointer;font:inherit;white-space:nowrap}
.df-menu button:hover,.df-menu button:focus{background:#3a5a8a;color:#fff;outline:none}.df-menu hr{border:none;border-top:1px solid #444;margin:3px 2px}
`;
let menu = null;
export const menuOpen = () => menu !== null;
export function closeMenu() {
  menu?.remove();
  menu = null;
}
document.addEventListener("mousedown", (event) => { if (menu && !menu.contains(event.target)) closeMenu(); }, true);

// The menu at a point (a mouse event's, or {clientX, clientY}), kept on the screen.
export function showMenu(point, items) {
  addStyleOnce("df-menu-style", STYLE);
  closeMenu();
  menu = element("div", { class: "df-menu", role: "menu" }, ...items.map((item) => (item === "-" ? element("hr") : element("button", { role: "menuitem", title: item[2] ?? "",
    onclick: () => { closeMenu(); background(Promise.resolve().then(item[1])); } }, item[0]))));
  document.body.append(menu);
  const box = menu.getBoundingClientRect();
  menu.style.left = `${Math.max(4, Math.min(point.clientX, innerWidth - box.width - 4))}px`;
  menu.style.top = `${Math.max(4, Math.min(point.clientY, innerHeight - box.height - 4))}px`;
  menu.querySelector("button")?.focus({ preventScroll: true }); // The keyboard (↑ ↓ Enter) works in it at once.
  menu.addEventListener("keydown", (event) => {
    const buttons = [...menu.querySelectorAll("button")], at = buttons.indexOf(document.activeElement);
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      buttons[(at + (event.key === "ArrowDown" ? 1 : buttons.length - 1)) % buttons.length]?.focus();
    }
  });
}
// Right-click on an element opens its menu; items() gives them at that moment (a star or a folder's state may have changed).
export function withMenu(target, items) {
  target.addEventListener("contextmenu", (event) => {
    event.preventDefault();
    event.stopPropagation();
    showMenu(event, items());
  });
  return target;
}
// The ⋯ button: the same menu, under the button (for the keyboard, touch screens, and who doesn't know the right-click).
export function menuButton(items, title = "More (or right-click)") {
  return element("button", { class: "more", title, onclick: (event) => {
    event.stopPropagation();
    const box = event.currentTarget.getBoundingClientRect();
    showMenu({ clientX: box.left, clientY: box.bottom }, items());
  } }, "⋯");
}
// The menu of an element opened from the keyboard (the menu key, or Shift+F10), at the element.
export function menuAt(target, items) {
  const box = target.getBoundingClientRect();
  showMenu({ clientX: box.left + 20, clientY: box.bottom }, items);
}

// Keys in the browsers: is the user typing in a field (where keys are text), and / to jump into the search box from anywhere else.
export const typingIn = (event) => !!event.target?.closest?.("input, textarea, select, [contenteditable='true']");
export function slashToSearch(event, search) {
  if (event.key !== "/" || event.ctrlKey || event.metaKey || event.altKey || typingIn(event)) return false;
  event.preventDefault();
  search.focus();
  search.select();
  return true;
}
// ↑ ↓ through rows: the next or previous one after the one marked .cursor (the first or last when none is), marked and scrolled to.
export function moveCursor(rows, step) {
  if (!rows.length) return null;
  const at = rows.findIndex((row) => row.classList.contains("cursor"));
  const next = rows[at < 0 ? (step > 0 ? 0 : rows.length - 1) : Math.max(0, Math.min(rows.length - 1, at + step))];
  rows.forEach((row) => row.classList.toggle("cursor", row === next));
  next.scrollIntoView({ block: "nearest" });
  return next;
}

// ? in a window: its keys, in a small window over it; any key or click closes it (before the window sees the key).
const KEYS_STYLE = `
.df-keys-back{position:fixed;inset:0;z-index:10004;display:flex;align-items:center;justify-content:center;background:rgba(0,0,0,.35)}
.df-keys{background:#262626;color:#ddd;border:1px solid #666;border-radius:8px;padding:12px 16px;font:13px system-ui,sans-serif;box-shadow:0 8px 30px #000b;min-width:320px}
.df-keys h3{margin:0 0 8px;font-size:15px;color:#fff}.df-keys table{border-collapse:collapse}.df-keys td{padding:3px 8px;vertical-align:top}
.df-keys kbd{background:#3a3a3a;border:1px solid #555;border-radius:4px;padding:0 5px;font:12px ui-monospace,monospace;white-space:nowrap}.df-keys .hint{color:#888;margin-top:8px}
`;
export function showKeys(title, keys) {
  addStyleOnce("df-keys-style", KEYS_STYLE);
  const back = element("div", { class: "df-keys-back" }, element("div", { class: "df-keys" }, element("h3", {}, `⌨ ${title}`),
    element("table", {}, ...keys.map(([key, what]) => element("tr", {}, element("td", {}, ...key.split(" / ").flatMap((part, index) => [...(index ? [" / "] : []), element("kbd", {}, part)])),
      element("td", {}, what)))), element("div", { class: "hint" }, "Any key or click closes this.")));
  const shut = (event) => {
    event.preventDefault();
    event.stopPropagation();
    back.remove();
    window.removeEventListener("keydown", shut, true);
  };
  window.addEventListener("keydown", shut, true); // Before the window's own keys: Escape closes only this.
  back.addEventListener("mousedown", shut);
  document.body.append(back);
}
// ? opens the keys (not while typing); the ⌨ button does too.
export function keysOnQuestion(event, title, keys) {
  if (event.key !== "?" || typingIn(event)) return false;
  event.preventDefault();
  showKeys(title, keys);
  return true;
}
export const keysButton = (title, keys) => element("button", { class: "keys", title: "The keyboard (or press ?)", onclick: () => showKeys(title, keys) }, "⌨");
