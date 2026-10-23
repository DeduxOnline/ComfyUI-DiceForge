// 🔁 Find and replace in the Wildcard Browser: in every wildcard, txt files and yaml keys, a preview of what changes first, then Replace (after a
// rename: the old name in the files that use it).
import { api } from "../../scripts/api.js";
import { askConfirm, background, element } from "./dom.js";

// say: a message in the browser; unsaved(): the open file has changes not saved; refresh(files): what changed is read and drawn again.
export function findAndReplace({ say, unsaved, refresh }) {
  const replacePanel = element("div", { class: "replace", hidden: "" });
  const findInput = element("input", { class: "find", placeholder: "Find (as written, case and all)" });
  const replaceInput = element("input", { class: "with", placeholder: "Replace with" });
  const replaceResults = element("div", { class: "results" });
  async function replaceCall(apply) {
    const response = await api.fetchApi("/diceforge/wildcards/replace", { method: "POST", body: JSON.stringify({ find: findInput.value, replace: replaceInput.value, apply }) });
    if (!response.ok) return say(await response.text());
    return response.json();
  }
  async function previewReplace() {
    const result = await replaceCall(false);
    if (!result) return;
    const count = result.files.reduce((sum, file) => sum + file.count, 0);
    replaceResults.replaceChildren(
      element("div", { class: "muted" }, result.files.length ? `${count} in ${result.files.length} wildcard${result.files.length === 1 ? "" : "s"}:` : "Not in any wildcard."),
      ...result.files.map((file) => element("div", { class: "change" }, element("b", {}, `${file.name} ×${file.count}`),
        element("span", { class: "before" }, file.line), element("span", { class: "after" }, file.after))),
      ...(result.files.length ? [element("button", { class: "apply", onclick: () => background(applyReplace(result.files.length)) }, `Replace in ${result.files.length} file${result.files.length === 1 ? "" : "s"}`)] : []));
  }
  async function applyReplace(fileCount) {
    if (unsaved()) return say("Save (or undo) the open file's changes first: the replace would change it under you.");
    if (!(await askConfirm(`Replace “${findInput.value}” with “${replaceInput.value}” in ${fileCount} file${fileCount === 1 ? "" : "s"}?`))) return;
    const result = await replaceCall(true);
    if (!result) return;
    await refresh(result.files);
    replaceResults.replaceChildren();
    say(`Replaced “${findInput.value}” with “${replaceInput.value}” in ${result.files.length} file${result.files.length === 1 ? "" : "s"}.`);
  }
  async function openReplace(find = findInput.value, replacement = replaceInput.value) {
    findInput.value = find;
    replaceInput.value = replacement;
    replacePanel.hidden = false;
    replaceResults.replaceChildren();
    if (find) await previewReplace();
    else findInput.focus();
  }
  for (const input of [findInput, replaceInput]) input.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); background(previewReplace()); } });
  replacePanel.append(element("div", { class: "replace-head" }, element("b", {}, "🔁"), findInput, element("span", {}, "→"), replaceInput,
    element("button", { class: "preview", onclick: () => background(previewReplace()) }, "Preview"),
    element("button", { class: "close-replace", title: "Close", onclick: () => { replacePanel.hidden = true; } }, "✕")), replaceResults);
  const replaceButton = element("button", { class: "replace-open", title: "Find and replace in every wildcard file (a preview first)", onclick: () => background(openReplace()) }, "🔁 Replace");
  return { panel: replacePanel, button: replaceButton, open: openReplace };
}
