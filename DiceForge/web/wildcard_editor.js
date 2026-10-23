// The wildcard files' editor in the Wildcard Browser: a textarea whose text a layer behind it draws with the syntax colored as in the prompt
// fields, line numbers, the caret's line marked, and + next to a line's number to put that line in the prompt.
import { element } from "./dom.js";
import { highlightEnabled, highlightWildcardFile } from "./prompt_highlight.js";
import { knownWildcards } from "./wildcards.js";

// optionOf(line): the option a line of the open file gives (a yaml file's line: its value); addLine(text, number): its + was clicked.
export function codeEditor({ optionOf, addLine }) {
  const editor = element("textarea", { class: "src dfwc-editor", placeholder: "One option per line", wrap: "off", spellcheck: "false" });
  // The text is drawn, with its syntax colored as in the prompt fields, by a layer behind the editor, whose own text is transparent (it keeps
  // the caret, selection and editing). The layer also draws the lines under the rows and the caret's line.
  const highlight = element("div", { class: "dfhl hl", "aria-hidden": "true" });
  const paint = () => {
    const text = editor.value;
    if (highlightEnabled() && text.length <= 300000) highlight.innerHTML = highlightWildcardFile(text, knownWildcards()); // A huge file: plain.
    else highlight.textContent = text + "\n";
    highlight.scrollTop = editor.scrollTop;
    highlight.scrollLeft = editor.scrollLeft;
  };
  // Line numbers next to the editor, as in a code editor, scrolled with it; lines don't wrap, so each number stays next to its line.
  const lines = element("div", { class: "lines", "aria-hidden": "true" }, "1");
  const numberLines = () => {
    const count = editor.value.split("\n").length;
    if (lines.dataset.count !== String(count)) {
      lines.dataset.count = String(count);
      lines.textContent = Array.from({ length: count }, (_, index) => index + 1).join("\n");
      lines.style.width = `${String(count).length}ch`;
    }
    lines.scrollTop = editor.scrollTop;
    paint();
  };
  editor.addEventListener("input", numberLines);
  editor.addEventListener("scroll", () => {
    lines.scrollTop = highlight.scrollTop = editor.scrollTop;
    highlight.scrollLeft = editor.scrollLeft;
  });
  // The line with the caret is highlighted, in the text and its number (a background row, scrolled with the text).
  const code = element("div", { class: "code" }, lines, element("div", { class: "text" }, highlight, editor));
  const markCurrentLine = () => {
    let line = 0;
    for (let at = editor.value.indexOf("\n"); at !== -1 && at < editor.selectionStart; at = editor.value.indexOf("\n", at + 1)) line++;
    code.style.setProperty("--current-line", `${6 + 20 * line}px`);
  };
  const onSelection = () => { if (document.activeElement === editor) markCurrentLine(); };
  document.addEventListener("selectionchange", onSelection);
  for (const type of ["input", "click", "keyup", "focus"]) editor.addEventListener(type, markCurrentLine);
  // + next to a line's number puts that line in the prompt (without its 3:: weight), where the cursor was in the node's fields.
  const lineAdd = element("button", { class: "line-add", hidden: true, title: "Add this line to the prompt" }, "+");
  code.append(lineAdd);
  const lineText = (index) => {
    const line = editor.value.split("\n")[index] ?? "";
    return optionOf(line).trim().replace(/^\d+(?:\.\d+)?::/, "").trim();
  };
  code.addEventListener("mousemove", (event) => {
    if (event.target === lineAdd) return;
    const index = Math.floor((event.clientY - code.getBoundingClientRect().top - 6 + editor.scrollTop) / 20);
    const text = lineText(index);
    lineAdd.hidden = !text || text.startsWith("#");
    lineAdd.dataset.line = String(index);
    lineAdd.style.top = `${6 + 20 * index - editor.scrollTop + 1}px`;
  });
  code.addEventListener("mouseleave", () => { lineAdd.hidden = true; });
  editor.addEventListener("scroll", () => { lineAdd.hidden = true; });
  lineAdd.addEventListener("click", () => {
    const text = lineText(Number(lineAdd.dataset.line));
    if (!text) return;
    addLine(text, Number(lineAdd.dataset.line) + 1);
  });
  const stop = () => document.removeEventListener("selectionchange", onSelection); // When the browser closes.
  return { editor, code, numberLines, markCurrentLine, stop };
}
