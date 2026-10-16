import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { askConfirm, askText, background } from "./dom.js";
import { onWildcardList, toast, wildcardList } from "./wildcards.js";

// Wildcard Note: a note (like ComfyUI's Note, it is not run with the workflow) to collect wildcard lines while you work, with the prompt fields'
// tools (the __ autocomplete, highlighting, the Wildcard Browser). 💾 Save to WildCard puts its lines into the wildcard file picked in its list:
// after the file's lines (the ones the file already has are left out), in place of them, or into a new file.
const NODE_TYPE = "DiceForgeWildcardNote";
const NEW_FILE = "＋ New file…";
const ADD = "add lines", REPLACE = "replace file";

const widgetOf = (node, name) => node.widgets?.find((widget) => widget.name === name);
// The wildcards a note can write to (txt files and yaml keys, a yaml key in its yaml file), after the new file.
const fileChoices = (list) => [NEW_FILE, ...(list?.files ?? []).map((file) => file.name)];
function showChoices(node, list) {
  const files = widgetOf(node, "wildcard");
  if (files) files.options.values = fileChoices(list);
}
// Every new wildcard list (a file made, renamed or deleted here or in the Wildcard Browser) reaches the notes' lists.
onWildcardList((list) => (app.graph?.nodes ?? []).filter((node) => node.comfyClass === NODE_TYPE).forEach((node) => showChoices(node, list)));

// The note's lines as a wildcard file's lines: trimmed, without empty lines and repeats.
const noteLines = (node) => [...new Set(String(widgetOf(node, "text")?.value ?? "").split("\n").map((line) => line.trim()).filter(Boolean))];
const linesWord = (count) => `${count} line${count === 1 ? "" : "s"}`;

// What the save writes ({ text, create, done }), or null when there is nothing to write (a message said why). A name without a file makes the
// file; replacing a file's lines is asked first.
async function plannedSave(name, lines, mode) {
  const file = await api.fetchApi(`/diceforge/wildcards/file?name=${encodeURIComponent(name)}`);
  if (file.status === 404) return { text: lines.join("\n"), create: true, done: `Made __${name}__ with the note's ${linesWord(lines.length)}` };
  if (!file.ok) {
    toast("error", await file.text());
    return null;
  }
  const current = await file.json();
  if (mode === REPLACE) {
    if (!(await askConfirm(`Replace the lines of __${name}__ with the note's ${linesWord(lines.length)}?`))) return null;
    return { text: lines.join("\n"), done: `Replaced the lines of __${name}__ with the note's ${linesWord(lines.length)}` };
  }
  const known = new Set(current.text.split("\n").map((line) => line.trim()));
  const added = lines.filter((line) => !known.has(line));
  if (!added.length) {
    toast("info", `__${name}__ already has every line of the note.`);
    return null;
  }
  const already = lines.length > added.length ? ` (${lines.length - added.length} already there)` : "";
  return { text: current.text.trim() ? `${current.text}\n${added.join("\n")}` : added.join("\n"), done: `Added ${linesWord(added.length)} to __${name}__${already}` };
}

async function saveToWildcard(node) {
  const lines = noteLines(node);
  if (!lines.length) return toast("warn", "The note is empty: write the wildcard's lines in it first, one per line.");
  const files = widgetOf(node, "wildcard");
  const name = files?.value && files.value !== NEW_FILE ? files.value
    : (await askText("A new wildcard file for the note's lines: its name (folders with /, for example outfit/dress):"))?.trim();
  if (!name) return;
  const plan = await plannedSave(name, lines, widgetOf(node, "mode")?.value);
  if (!plan) return;
  const response = await api.fetchApi("/diceforge/wildcards/file", { method: "POST", body: JSON.stringify({ name, text: plan.text, create: plan.create === true }) });
  if (!response.ok) return toast("error", await response.text());
  files.value = (await response.json()).saved; // The file the next save goes to (a new file's name, as the server wrote it).
  showChoices(node, await wildcardList(true));
  node.setDirtyCanvas?.(true, true);
  toast("success", `${plan.done}.`);
}

app.registerExtension({
  name: "DiceForge.WildcardNote",
  // Registered here, when ComfyUI's LiteGraph and widgets are ready, as ComfyUI registers its own Note.
  registerCustomNodes() {
    const { LGraphNode, LGraphCanvas, LiteGraph } = window;
    class WildcardNote extends LGraphNode {
      constructor(title) {
        super(title);
        this.comfyClass = NODE_TYPE; // For the prompt tools (wildcards.js PROMPT_NODES) and the notes' list updates.
        this.color = LGraphCanvas.node_colors.yellow.color;
        this.bgcolor = LGraphCanvas.node_colors.yellow.bgcolor;
        window.comfyAPI.widgets.ComfyWidgets.STRING(this, "text", ["STRING", { multiline: true, placeholder: "One wildcard line per line" }], app);
        this.addWidget("combo", "wildcard", NEW_FILE, () => {}, { values: fileChoices(null) });
        this.addWidget("combo", "mode", ADD, () => {}, { values: [ADD, REPLACE] });
        this.addWidget("button", "💾 Save to WildCard", null, () => background(saveToWildcard(this)), { serialize: false });
        this.setSize([380, 300]); // Room for a few lines in the text field (a loaded workflow sets its own size).
        this.serialize_widgets = true;
        this.isVirtualNode = true; // Not sent with the workflow's prompt: nothing runs it.
        background(wildcardList().then((list) => showChoices(this, list)));
      }
    }
    LiteGraph.registerNodeType(NODE_TYPE, Object.assign(WildcardNote, { title: "Wildcard Note", title_mode: LiteGraph.NORMAL_TITLE, collapsable: true }));
    WildcardNote.category = "DiceForge/utils";
  },
  getNodeMenuItems(node) {
    return node.comfyClass === NODE_TYPE ? [{ content: "↻ Refresh the file list", callback: () => background(wildcardList(true)) }] : [];
  },
});
