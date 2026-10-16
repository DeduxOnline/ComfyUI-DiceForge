import { addStyleOnce, asking, background, element } from "./dom.js";
import { insertIntoNode } from "./wildcards.js";
import { keepSize, recall, remember, scrollBack } from "./window_memory.js";
import { keysButton, keysOnQuestion, slashToSearch } from "./menu.js";
const SYNTAX_KEYS = [["/", "Jump to the search"], ["Esc", "Close"], ["?", "These keys"]];

// Syntax guide (CLIP Dual Text Encode's menu): every piece of the prompt syntax with what it does and an example. A click on an example copies it;
// + Insert puts it where the cursor was in the node's prompts. The search box filters the rows.
const STYLE = `
.dfsg-back{position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:10000;display:flex;align-items:center;justify-content:center}
.dfsg{background:#353535;color:#ddd;border:1px solid #555;border-radius:10px;width:min(980px,95vw);height:min(840px,92vh);display:flex;flex-direction:column;gap:8px;padding:14px 16px;font:14px system-ui,sans-serif;box-shadow:0 10px 40px #000a;box-sizing:border-box}
.dfsg h2{margin:0;font-size:20px;color:#fff}.dfsg .top{display:flex;gap:8px;align-items:center}.dfsg .top input{flex:1}
.dfsg input{background:#262626;color:#eee;border:1px solid #555;border-radius:4px;padding:6px 8px;font:inherit}
.dfsg button{background:#222;color:#eee;border:1px solid #666;border-radius:6px;padding:4px 10px;cursor:pointer;font:inherit}.dfsg button:hover{background:#2c2c2c}
.dfsg .body{flex:1;overflow:auto;padding-right:4px}.dfsg h3{margin:14px 0 6px;font-size:15px;color:#9cc8ff}.dfsg h3:first-child{margin-top:0}
.dfsg .row{display:grid;grid-template-columns:minmax(150px,230px) 1fr auto;gap:10px;align-items:start;padding:6px 4px;border-bottom:1px solid #3d3d3d}.dfsg .row>code{justify-self:start}
.dfsg code{font:13px ui-monospace,monospace;background:#262626;border:1px solid #484848;border-radius:4px;padding:1px 5px;color:#ffcf5c;white-space:pre-wrap;word-break:break-word}
.dfsg .what{color:#ccc;font-size:13px}.dfsg .what code{color:#ddd}.dfsg .example{display:block;margin-top:4px;cursor:copy}.dfsg .example.copied{border-color:#6a9a6a}
.dfsg .row button{padding:2px 8px;font-size:12px;border-color:#4a7a4a;color:#bfe8bf;white-space:nowrap}.dfsg .note{color:#999;font-size:13px;margin:2px 0 6px}
.dfsg .status{color:#9c9;font-size:13px;min-height:18px}.dfsg .empty{color:#999;padding:12px}
`;
// [section, [syntax, what it does, example (inserted), note?]]
export const GUIDE = [
  ["Wildcards", [
    ["__name__", "A random line of the wildcard file name.txt (ComfyUI/models/wildcards). Typing __ opens the list of files.", "__color__ hair"],
    ["__folder/name__", "A file in a subfolder.", "__styles/photo__"],
    ["__folder/*__", "All the files of a folder as one list; * is any text, ? one character.", "__hair/*__"],
    ["{2$$__name__}", "Two different lines of the file.", "{2$$__accessory__}"],
  ]],
  ["Choices", [
    ["{a|b|c}", "One of the options; options can be empty and can nest.", "{red|green|blue} dress"],
    ["{3::a|b}", "A weight: a is 3 times as likely as b (options without one count as 1).", "{3::cat|dog}"],
    ["{2$$a|b|c}", "Two different options, joined with a comma.", "{2$$hat|scarf|bow}"],
    ["{1-3$$a|b|c}", "From 1 to 3 options; -2$$ is 0 to 2, 2-$$ is 2 up to all.", "{1-3$$hat|scarf|bow}"],
    ["{2$$ and $$a|b|c}", "Two options joined with \" and \" instead of a comma.", "{2$$ and $$red|blue|gold}"],
    ["{a|!b|c}", "A lock: always b, in every seed mode; remove the ! to unlock.", "{sky|!sea|forest}"],
  ]],
  ["Variables", [
    ["${name=...}", "Sets a variable (filled in once, outputs nothing); ${name=!...} works the same.", "${hair=__color__}"],
    ["${name}", "The variable's value, anywhere in either prompt.", "${hair=__color__}${hair} hair, ${hair} ribbon"],
    ["__folder/${name}__", "A variable in a wildcard name: related parts match (not in combinations).", "${g={male|female}}__outfit/${g}__"],
  ]],
  ["LoRAs and weights", [
    ["<lora:name:0.8>", "Puts the LoRA on the model and the CLIP (connect model in and out). <lora:name> is weight 1.", "<lora:name:0.8>"],
    ["<lora:name:0.8:0.5>", "Model and CLIP weights apart; <lyco:...> works the same.", "<lora:name:0.8:0.5>"],
    ["(word:1.2)", "A prompt weight, as in the core node; embedding:name works too.", "(detailed background:1.2)"],
  ]],
  ["Comments and escapes", [
    ["// text", "A comment to the end of the line, removed before encoding.", "// lighting ideas"],
    ["/* text */", "A comment anywhere, also over several lines.", "/* unused: rain */"],
    ["\\{ \\} \\| \\!", "A brace, bar or ! as plain text.", "\\{not a choice\\}"],
  ]],
  ["Wildcard files", [
    ["one option per line", "Empty lines and lines starting with # are skipped; files are UTF-8.", "# colors\ncrimson red\ndeep {navy|royal} blue"],
    ["3::line", "A line's weight in its file; 0:: turns a line off.", "3::black"],
    ["YAML", "Nested keys are folders, each list a wildcard: characters.yaml with alice: outfit: [...] is __characters/alice/outfit__.", "__characters/alice/outfit__"],
  ]],
];
const MODES = "Seed modes (Advanced): random · deck (every option once per round, with increment) · shuffle · balanced · combinations (seeds 0, 1, 2… go through every prompt) · mutate (one choice changes per run).";

export function openSyntaxGuide(node) {
  addStyleOnce("dfsg-style", STYLE);
  const search = element("input", { placeholder: "Search the syntax…" });
  const body = element("div", { class: "body" });
  const status = element("div", { class: "status" });
  const back = element("div", { class: "dfsg-back" });
  const onKey = (event) => {
    if (asking()) return;
    if (event.key === "Escape") {
      event.stopPropagation();
      close();
    } else if (!keysOnQuestion(event, "Prompt syntax", SYNTAX_KEYS)) slashToSearch(event, search); // / to the search box.
  };
  function close() {
    remember("syntax", { search: search.value, scroll: body.scrollTop }); // Opens where it was closed.
    stopSize();
    back.remove();
    document.removeEventListener("keydown", onKey, true);
  }
  back.addEventListener("mousedown", (event) => { if (event.target === back) close(); });
  document.addEventListener("keydown", onKey, true);
  function row([syntax, what, example]) {
    const sample = element("code", { class: "example", title: "Click to copy" }, example);
    sample.addEventListener("click", () => {
      background(navigator.clipboard?.writeText(example)); // A refused copy (no permission) is logged, not thrown.
      sample.classList.add("copied");
      setTimeout(() => sample.classList.remove("copied"), 600);
    });
    return element("div", { class: "row" }, element("code", {}, syntax), element("div", { class: "what" }, what, sample),
      element("button", { title: "Put the example where the cursor was in the prompts", onclick: () => {
        const field = insertIntoNode(node, example);
        status.textContent = `Inserted into the ${field} prompt.`;
      } }, "+ Insert"));
  }
  function draw() {
    const words = search.value.trim().toLowerCase();
    const fits = (entry) => !words || entry.join(" ").toLowerCase().includes(words);
    const sections = GUIDE.map(([title, entries]) => [title, entries.filter(fits)]).filter(([, entries]) => entries.length);
    body.replaceChildren(...(sections.length ? sections.flatMap(([title, entries]) => [element("h3", {}, title), ...entries.map(row)])
      : [element("div", { class: "empty" }, "Nothing matches.")]), element("div", { class: "note" }, MODES));
  }
  search.addEventListener("input", draw);
  const heading = element("h2", {}, "Prompt syntax"), dialog = element("div", { class: "dfsg" });
  const stopSize = keepSize(dialog, "syntax", heading);
  back.append(dialog);
  dialog.append(heading,
    element("div", { class: "top" }, search, keysButton("Prompt syntax", SYNTAX_KEYS), element("button", { onclick: close }, "Close")), body, status);
  const last = recall("syntax");
  search.value = typeof last.search === "string" ? last.search : "";
  document.body.append(back);
  draw();
  search.focus();
  search.setSelectionRange(search.value.length, search.value.length);
  scrollBack(body, last.scroll);
}
// In the menu through wildcards.js (first among the prompt tools).
