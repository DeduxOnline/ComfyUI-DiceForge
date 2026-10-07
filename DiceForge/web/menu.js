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
