// End-to-end in the browser, the prompts: autocomplete, syntax highlighting, the Wildcard Browser, Wildcards to Text, Wildcard Note, the Syntax guide,
// prompt styles, the tag autocomplete, the prompt preview and history, and Danbooru Tag Enhancer, in both node designs (Nodes 2.0 and
// classic), against the real server. Each test builds its own graph.
const fs = require("fs");
const { test, expect, basePath, writeFile, openComfy, drawn, addNodes, connect, widgetValue, setWidget, menuItems, clickMenu, queueFromPage, nodeElement, answerQuestions } = require("./helpers");
const { png, zip } = require("./fixtures");
const { promptField, lookUp, wildcardMode } = require("./ui-shared");

for (const vue of [true, false]) {
  test.describe(vue ? "Nodes 2.0" : "classic nodes", () => {
    test.beforeEach(async ({ page }) => openComfy(page, { vue }));

    test("typing __ in CLIP Dual Text Encode suggests wildcards", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      const positive = await promptField(page, id, "positive");
      await positive.click();
      await page.keyboard.type("1girl, __hair/st");
      await expect(page.locator(".dfwc-pop")).toContainText("__hair/style__");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, __hair/style__");
      await expect(page.locator(".dfwc-pop")).toHaveCount(0);
      await page.keyboard.type(", __col");
      await expect(page.locator(".dfwc-pop div").first()).toContainText("__color__");
      await page.keyboard.press("Escape");
      await expect(page.locator(".dfwc-pop")).toHaveCount(0);
      await positive.fill("");
      await page.keyboard.type("__цв"); // Not only Latin letters.
      await expect(page.locator(".dfwc-pop div").first()).toContainText("__цвет__");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("__цвет__");
      await page.keyboard.type(", <lora:in"); // LoRA files after <lora:
      await expect(page.locator(".dfwc-pop div").first()).toContainText("style/ink");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("__цвет__, <lora:style/ink:1>");
    });

    test("the autocomplete opens under the caret, also on a zoomed canvas and on a later line", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [100, 60], widgets: {
        positive: "masterpiece, best quality, 1girl, __color__ hair, multiple views, dynamic pose, from above, standing, looking at viewer, long hair" } }]);
      await page.evaluate(() => { window.app.canvas.ds.scale = 1.5; window.app.canvas.setDirty(true, true); });
      await drawn(page); // The field is placed for the new zoom.
      const positive = await promptField(page, id, "positive");
      await positive.click();
      await page.keyboard.press("Control+End");
      await page.keyboard.type(", __co");
      const popupBox = await page.locator(".dfwc-pop").boundingBox();
      const box = await positive.evaluate((field) => { // The field's box on the screen: the caret is on its last line, after some text.
        const rect = field.getBoundingClientRect();
        return { right: rect.right, bottom: rect.bottom, top: rect.top, left: rect.left };
      });
      expect(popupBox.y).toBeGreaterThan(box.top + 20); // Under a later line, not the first.
      expect(popupBox.y).toBeLessThan(box.bottom + 40); // Right under the text, not far below the field.
      expect(popupBox.x).toBeGreaterThan(box.left + 100); // At the caret, not at the start of the line.
    });

    test("autocomplete follows the text as typed while the wildcard list loads slowly", async ({ page }) => {
      let requests = 0, answered = 0;
      await page.route("**/diceforge/wildcards", async (route) => {
        const delay = [900, 300, 50][Math.min(requests++, 2)]; // Later requests answer sooner: answers come back out of order.
        await new Promise((resolve) => setTimeout(resolve, delay));
        await route.continue();
        answered++;
      });
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      const positive = await promptField(page, id, "positive");
      await positive.click();
      await page.keyboard.type("__hair/st");
      await expect.poll(() => answered).toBe(requests); // Every answer is in.
      await expect(page.locator(".dfwc-pop div").first()).toContainText("__hair/style__");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("__hair/style__");
      expect(requests).toBe(1); // One shared request, not one per keystroke.
    });

    test("the prompt fields highlight the syntax, with missing wildcards in red", async ({ page }) => {
      const prompt = "${g={male|female}}a __color__ {2$$3::!hat|__nope__|bow} \\{x\\} (smile:1.2) ${g} // note\n/* block */ embedding:easy";
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", widgets: { positive: prompt } }]);
      const field = await promptField(page, id, "positive");
      const layer = field.locator("xpath=preceding-sibling::div[contains(concat(' ', @class, ' '), ' dfhl ')][1]");
      await expect(layer).toHaveCount(1);
      const marked = async (kind) => layer.locator(`span.${kind}`).allTextContents();
      await expect.poll(() => marked("wc")).toEqual(["__color__"]);
      expect(await marked("wc-missing")).toEqual(["__nope__"]); // No wildcard file nope.txt.
      expect(await marked("count")).toEqual(["2$$"]);
      expect(await marked("weight")).toEqual(["3::"]);
      expect(await marked("lock")).toEqual(["!"]);
      expect(await marked("var")).toEqual(["${g=", "}", "${g}"]);
      expect(await marked("b0")).toEqual(["{", "|", "|", "}"]); // A choice at the top.
      expect(await marked("b1")).toEqual(["{", "|", "}"]); // One inside ${g=...}: one level down, another color.
      expect(await marked("esc")).toEqual(["\\{", "\\}"]);
      expect(await marked("attn")).toEqual([":1.2"]);
      expect(await marked("comment")).toEqual(["// note", "/* block */"]);
      expect(await marked("embed")).toEqual(["embedding:easy"]);
      expect(await layer.textContent()).toBe(`${prompt}\n`); // The same text, only colored.
      await expect(field).toHaveAttribute("title", "No wildcard file for __nope__");
      expect(await field.evaluate((element) => getComputedStyle(element).webkitTextFillColor)).toBe("rgba(0, 0, 0, 0)"); // The field shows the layer.
      const [box, inner] = [await field.boundingBox(), await layer.boundingBox()];
      expect(Math.abs(box.x - inner.x)).toBeLessThan(3);
      expect(Math.abs(box.width - inner.width)).toBeLessThan(20); // Inside the field's border, without its scrollbar.
      await field.click();
      await page.keyboard.press("ControlOrMeta+a");
      await page.keyboard.type("{a|{b|c}} {unclosed");
      await expect.poll(() => marked("b1")).toEqual(["{", "|", "}"]); // Nested: another color.
      expect(await marked("bad")).toEqual(["{"]); // Never closed.
      await expect(field).not.toHaveAttribute("title", /No wildcard/);
      await page.evaluate(() => window.app.extensionManager.setting.set("DiceForge.PromptHighlight", false));
      await expect(layer).toHaveCount(0); // Off: the plain field again.
      expect(await field.evaluate((element) => element.classList.contains("dfhl-input"))).toBe(false);
      await page.evaluate(() => window.app.extensionManager.setting.set("DiceForge.PromptHighlight", true));
      await expect(field.locator("xpath=preceding-sibling::div[contains(concat(' ', @class, ' '), ' dfhl ')][1]")).toHaveCount(1);
    });

    test("Wildcard Browser adds wildcards to the prompt and edits files", async ({ page }) => {
      writeFile(`models/wildcards/edit_${vue ? "vue" : "classic"}.txt`, "one\ntwo\n");
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60], widgets: { positive: "1girl" } }]);
      expect(await menuItems(page, id, "DiceForge.Wildcards")).toEqual(["📖 Syntax guide", "🎲 Wildcard Browser", "✂ Selection → new wildcard…"]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      await expect(page.locator(".dfwc .row").first()).toBeVisible();
      await page.locator(".dfwc .tree > .row", { hasText: /^color/ }).locator("button.add").click(); // color.txt at the top, not hair/color.txt.
      await page.locator(".dfwc .folder > .row", { hasText: "hair" }).first().locator("button.add").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, __color__, __hair/*__");
      const file = `edit_${vue ? "vue" : "classic"}`; // A file of its own: the tests share the server's files.
      await page.locator(".dfwc .row", { hasText: file }).locator(".name").click();
      await expect(page.locator(".dfwc .edit textarea")).toHaveValue("one\ntwo");
      const numbers = () => page.locator(".dfwc .code .lines").evaluate((gutter) => gutter.textContent);
      await expect.poll(numbers).toBe("1\n2"); // A line number next to each line.
      await page.locator(".dfwc .edit textarea").fill("one\ntwo\n2::three");
      await expect.poll(numbers).toBe("1\n2\n3"); // Numbered again as you type.
      await expect(page.locator(".dfwc .code .hl .weight")).toHaveText("2::"); // The syntax colored, as in the prompt fields: the line's weight.
      const currentLine = () => page.locator(".dfwc .code").evaluate((code) => code.style.getPropertyValue("--current-line"));
      await expect.poll(currentLine).toBe("46px"); // The caret's line (the third, after typing) is highlighted.
      await page.locator(".dfwc .edit textarea").press("Control+Home");
      await expect.poll(currentLine).toBe("6px"); // And follows the caret.
      await page.locator(".dfwc button", { hasText: "Save" }).click();
      await expect(page.locator(".dfwc .status")).toContainText(`Saved ${file}.txt`);
      expect(fs.readFileSync(basePath("models", "wildcards", `${file}.txt`), "utf8")).toBe("one\ntwo\n2::three\n");
      await page.keyboard.press("Escape");
      await expect(page.locator(".dfwc")).toHaveCount(0);
    });

    test("Wildcard Browser folders open and close, and stay so", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      await page.evaluate(() => localStorage.removeItem("diceforge.wildcards.open"));
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const hair = page.locator('.dfwc .folder[data-path="hair"]');
      const style = hair.locator(".row", { hasText: "style" });
      await expect(hair).not.toHaveClass(/open/); // Folders start closed.
      const [treeWidth, mainWidth] = await page.evaluate(() => [".dfwc .tree", ".dfwc .main"].map((selector) => document.querySelector(selector).offsetWidth));
      expect(Math.abs(treeWidth * 3 + 12 - mainWidth)).toBeLessThan(4); // The tree a third, the editor two thirds (12px between them).
      await expect(style).toBeHidden();
      await hair.locator("> .row .name").click();
      await expect(style).toBeVisible();
      await page.keyboard.press("Escape");
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      await expect(style).toBeVisible(); // Still open when the browser opens again.
      await page.locator(".dfwc button.close-all").click();
      await expect(style).toBeHidden();
      await page.locator(".dfwc .top input").first().fill("sty"); // A search shows the matches in their folders.
      await expect(style).toBeVisible();
      await page.locator(".dfwc .top input").first().fill("");
      await expect(style).toBeHidden();
      await page.locator(".dfwc button.open-all").click();
      await expect(page.locator('.dfwc .row[data-name="pack.yaml"]')).toContainText("yaml · 2 wildcards"); // A yaml file: one row, whole.
      await page.locator(".dfwc button.close-all").click();
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser moves files: Move picks a folder, a file dropped on a folder moves there", async ({ page }) => {
      const top = `wmove_${vue ? "vue" : "classic"}`, wildcards = (...parts) => basePath("models", "wildcards", ...parts);
      writeFile(`models/wildcards/${top}/from/x.txt`, "one\ntwo\n");
      writeFile(`models/wildcards/${top}/to/y.txt`, "y\n");
      try {
        const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
        await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
        await page.locator(".dfwc button.open-all").click();
        await page.locator(`.dfwc .row[data-name="${top}/from/x"] .name`).click();
        await expect(page.locator(".dfwc .edit textarea")).toHaveValue("one\ntwo"); // Opened (else the file, loading, replaces the typing).
        await page.locator(".dfwc .edit textarea").fill("one\ntwo\nthree"); // Unsaved: stays in the editor through the move.
        await page.locator(".dfwc button.move").click();
        await page.locator(`.dfmv .item[data-folder="${top}/to"]`).click();
        await expect(page.locator(".dfwc .status")).toContainText(`Moved ${top}/from/x to ${top}/to/x`);
        await expect(page.locator(".dfwc .edit textarea")).toHaveValue("one\ntwo\nthree");
        await expect(page.locator(".dfwc button.save")).toHaveText("Save •");
        expect(fs.readFileSync(wildcards(top, "to", "x.txt"), "utf8")).toBe("one\ntwo\n");
        expect(fs.existsSync(wildcards(top, "from"))).toBe(false);
        await page.locator(`.dfwc .row[data-name="${top}/to/y"]`).dragTo(page.locator(`.dfwc .folder[data-path="${top}"] > .row`));
        await expect(page.locator(".dfwc .status")).toContainText(`Moved ${top}/to/y to ${top}/y`);
        expect(fs.existsSync(wildcards(top, "y.txt"))).toBe(true);
        await page.locator(".dfwc button.move").click();
        await page.keyboard.press("Escape"); // Cancels the picker only.
        await expect(page.locator(".dfmv")).toHaveCount(0);
        await expect(page.locator(".dfwc")).toHaveCount(1);
        await page.locator(".dfwc button.close-all").click();
        await page.keyboard.press("Escape");
      } finally {
        fs.rmSync(wildcards(top), { recursive: true, force: true });
      }
    });

    test("Wildcard Browser opens where it was closed: the search, the open file with its unsaved changes", async ({ page }) => {
      const top = `wmem_${vue ? "vue" : "classic"}`;
      writeFile(`models/wildcards/${top}/notes.txt`, "alpha\nbeta\n");
      try {
        const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
        await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
        await page.locator(".dfwc .top input").first().fill(top);
        await page.locator(`.dfwc .row[data-name="${top}/notes"] .name`).click();
        await expect(page.locator(".dfwc .edit textarea")).toHaveValue("alpha\nbeta");
        await page.locator(".dfwc .edit textarea").fill("alpha\nbeta\ngamma");
        await page.locator(".dfwc .top button", { hasText: "Close" }).click();
        await expect(page.locator(".dfwc")).toHaveCount(0);
        await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
        await expect(page.locator(".dfwc .top input").first()).toHaveValue(top);
        await expect(page.locator(`.dfwc .row.sel[data-name="${top}/notes"]`)).toBeVisible();
        await expect(page.locator(".dfwc .edit textarea")).toHaveValue("alpha\nbeta\ngamma"); // Not saved, still there.
        await expect(page.locator(".dfwc button.save")).toHaveText("Save •");
        expect(fs.readFileSync(basePath("models", "wildcards", top, "notes.txt"), "utf8")).toBe("alpha\nbeta\n");
        await page.locator(".dfwc button.save").click();
        await expect(page.locator(".dfwc .status")).toContainText(`Saved ${top}/notes.txt`);
        await page.locator(".dfwc .top button", { hasText: "Close" }).click();
        writeFile(`models/wildcards/${top}/notes.txt`, "changed on disk\n");
        await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
        await expect(page.locator(".dfwc .edit textarea")).toHaveValue("changed on disk"); // Saved: the file as it is now.
        await expect(page.locator(".dfwc button.save")).toHaveText("Save");
        await page.locator(".dfwc .top button", { hasText: "Close" }).click();
      } finally {
        fs.rmSync(basePath("models", "wildcards", top), { recursive: true, force: true });
      }
    });

    test("Wildcard Browser: ⚠ broken references, a rename updates the files that use it, clean up and sort, the keyboard", async ({ page }) => {
      const top = `fix_${vue ? "vue" : "classic"}`, file = (...parts) => basePath("models", "wildcards", top, ...parts);
      writeFile(`models/wildcards/${top}/colour.txt`, "red\nblue\n");
      writeFile(`models/wildcards/${top}/look.txt`, `# looks\n__${top}/colour__ hair\n\nsmile\nsmile\n2::angry\n`);
      writeFile(`models/wildcards/${top}/list.txt`, "b\n3::a\nC\n");
      try {
        const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
        await answerQuestions(page, ({ prompt }) => (prompt ? `${top}/color` : true));
        await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
        const dialog = page.locator(".dfwc"), status = dialog.locator(".status"), row = (name) => dialog.locator(`.row[data-name="${top}/${name}"]`);
        await wildcardMode(dialog, "lines"); // Lines: the editor.
        await dialog.locator("button.open-all").click();
        await row("colour").click({ button: "right" }); // Renamed: look.txt now uses a name no file has.
        await page.locator(".df-menu button", { hasText: "✎ Rename…" }).click();
        await expect(status).toContainText(`Renamed ${top}/colour to ${top}/color`);
        await expect(row("look").locator(".broken")).toHaveAttribute("title", `Uses wildcards that don't exist: __${top}/colour__`);
        await dialog.locator("button.only-broken").click(); // ⚠ Broken: only such files.
        await expect(row("look")).toBeVisible();
        await expect(row("list")).toBeHidden();
        await dialog.locator("button.only-broken").click();
        await status.locator("button.more-action").click(); // 🔁 Update the files that use it: a preview, then Replace.
        await expect(dialog.locator(".replace .find")).toHaveValue(`__${top}/colour__`);
        await expect(dialog.locator(".replace .change")).toHaveText([`${top}/look ×1__${top}/colour__ hair__${top}/color__ hair`]);
        await dialog.locator(".replace button.apply").click();
        await expect(status).toContainText("in 1 file");
        expect(fs.readFileSync(file("look.txt"), "utf8")).toContain(`__${top}/color__ hair`);
        await expect(row("look").locator(".broken")).toHaveCount(0);
        await row("look").locator("button.more").click(); // 🧹 Clean up in the editor (not saved yet).
        await page.locator(".df-menu button", { hasText: "🧹 Remove duplicates and empty lines" }).click();
        await expect(dialog.locator(".edit textarea")).toHaveValue(`# looks\n__${top}/color__ hair\nsmile\n2::angry`);
        await expect(status).toContainText("1 duplicate and 1 empty line dropped");
        await dialog.locator("button.save").click();
        await expect(status).toContainText(`Saved ${top}/look.txt`);
        await row("list").click({ button: "right" });
        await page.locator(".df-menu button", { hasText: "🔤 Sort lines" }).click();
        await expect(dialog.locator(".edit textarea")).toHaveValue("3::a\nb\nC"); // By the text, the weight left aside.
        await expect(dialog.locator("button.save")).toHaveText("Save •");
        await setWidget(page, id, "positive", "1girl,\nsmile"); // ⇦ The prompt as a new line (its line break a space), not twice.
        await row("list").click({ button: "right" });
        await page.locator(".df-menu button", { hasText: "⇦ Add the prompt as a line" }).click();
        await expect(dialog.locator(".edit textarea")).toHaveValue("3::a\nb\nC\n1girl, smile");
        await expect(status).toContainText(`Added the positive prompt to ${top}/list as line 4.`);
        await dialog.locator("button.from-prompt").click();
        await expect(status).toContainText(`${top}/list already has the positive prompt as a line.`);
        // The keyboard: / to the search, ↓ to a file, Enter puts it in the prompt.
        await dialog.locator("h2").click();
        await page.keyboard.press("/");
        await expect(dialog.locator(".top input").first()).toBeFocused();
        await page.keyboard.type(`${top}/color`);
        await page.keyboard.press("ArrowDown");
        await expect(row("color")).toHaveClass(/cursor/);
        await page.keyboard.press("Enter");
        await expect.poll(() => widgetValue(page, id, "positive")).toBe(`1girl,\nsmile, __${top}/color__`);
        await dialog.locator(".top button", { hasText: "Close" }).click();
      } finally {
        fs.rmSync(file(), { recursive: true, force: true });
      }
    });

    test("✂ Selection → new wildcard: the selected part of the prompt becomes a wildcard, __name__ takes its place; a taken name gets it as a line", async ({ page }) => {
      const top = `cut_${vue ? "vue" : "classic"}`, file = (...parts) => basePath("models", "wildcards", top, ...parts);
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60], widgets: { positive: "1girl, red dress, smile" } }]);
      const field = await promptField(page, id, "positive");
      const select = async (from, to) => {
        await field.click();
        await field.evaluate((textarea, [from, to]) => textarea.setSelectionRange(from, to), [from, to]);
        await page.keyboard.up("Shift"); // A key up: the selection is remembered, as when the field loses focus.
      };
      const answers = [`${top}/dress`, `${top}/dress`];
      await answerQuestions(page, ({ prompt }) => (prompt ? answers.shift() : true));
      try {
        await clickMenu(page, id, "DiceForge.Wildcards", "Selection → new wildcard"); // Nothing selected: a message, nothing done.
        await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, red dress, smile");
        await select(7, 16); // "red dress"
        await clickMenu(page, id, "DiceForge.Wildcards", "Selection → new wildcard");
        await expect.poll(() => widgetValue(page, id, "positive")).toBe(`1girl, __${top}/dress__, smile`);
        expect(fs.readFileSync(file("dress.txt"), "utf8")).toBe("red dress\n");
        const text = await widgetValue(page, id, "positive");
        await select(text.length - 5, text.length); // "smile": the name is taken, so one more line of it.
        await clickMenu(page, id, "DiceForge.Wildcards", "Selection → new wildcard");
        await expect.poll(() => widgetValue(page, id, "positive")).toBe(`1girl, __${top}/dress__, __${top}/dress__`);
        expect(fs.readFileSync(file("dress.txt"), "utf8")).toBe("red dress\nsmile\n");
      } finally {
        fs.rmSync(file(), { recursive: true, force: true });
      }
    });

    test("Wildcard Note: 💾 Save to WildCard adds its new lines to the picked file, replaces the file's lines, or makes a new file", async ({ page }) => {
      const top = `note_${vue ? "vue" : "classic"}`, file = (...parts) => basePath("models", "wildcards", top, ...parts);
      writeFile(`models/wildcards/${top}/colors.txt`, "# my colors\nred\nblue\n");
      const answers = [`${top}/fresh`];
      await answerQuestions(page, ({ prompt }) => (prompt ? answers.shift() : true));
      const [id] = await addNodes(page, [{ type: "DiceForgeWildcardNote", pos: [300, 60], widgets: { text: "blue\n  green  \n\nyellow\ngreen" } }]);
      const choices = () => page.evaluate((id) => window.app.graph.getNodeById(id).widgets.find((widget) => widget.name === "wildcard").options.values, id);
      const text = (name) => (fs.existsSync(file(name)) ? fs.readFileSync(file(name), "utf8") : null);
      const save = async () => {
        if (vue) await nodeElement(page, id).getByRole("button", { name: /Save to WildCard/ }).click(); // The button in the node.
        else await page.evaluate((id) => window.app.graph.getNodeById(id).widgets.find((widget) => widget.type === "button").callback(), id);
      };
      try {
        await expect.poll(choices).toContain(`${top}/colors`);
        expect((await choices())[0]).toBe("＋ New file…");
        expect(await choices()).toContain("characters/alice/outfit"); // A yaml key too: saved into its yaml file.
        await setWidget(page, id, "wildcard", `${top}/colors`);
        await save(); // Added: the lines the file doesn't have yet, each once; its comment stays.
        await expect.poll(() => text("colors.txt")).toBe("# my colors\nred\nblue\ngreen\nyellow\n");
        await save(); // Nothing new: the file stays as it is.
        await page.waitForTimeout(500);
        expect(text("colors.txt")).toBe("# my colors\nred\nblue\ngreen\nyellow\n");
        await setWidget(page, id, "mode", "replace file");
        await save(); // Replaced, once confirmed.
        await expect.poll(() => text("colors.txt")).toBe("blue\ngreen\nyellow\n");
        await setWidget(page, id, "wildcard", "＋ New file…");
        await setWidget(page, id, "mode", "add lines");
        await save(); // A new file, named in the prompt.
        await expect.poll(() => text("fresh.txt")).toBe("blue\ngreen\nyellow\n");
        expect(answers).toEqual([]);
        expect(await widgetValue(page, id, "wildcard")).toBe(`${top}/fresh`); // The next save goes to it,
        await expect.poll(choices).toContain(`${top}/fresh`); // and the list has it.
        await setWidget(page, id, "text", "  \n");
        await save(); // An empty note writes nothing.
        await page.waitForTimeout(500);
        expect(text("fresh.txt")).toBe("blue\ngreen\nyellow\n");
        // A note is not part of a run: the prompt sent to the server doesn't have it.
        expect(await page.evaluate(async (id) => String(id) in (await window.app.graphToPrompt()).output, id)).toBe(false);
      } finally {
        fs.rmSync(file(), { recursive: true, force: true });
      }
    });

    test("Wildcard Note has a description and DiceForge as its source (badge, node library), not frontend_only", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeWildcardNote", pos: [300, 60] }]);
      // ComfyUI's node definitions (the store its badges, node library and help read), as the frontend made them for each node.
      const facts = await page.evaluate(() => {
        const pinia = [...document.querySelectorAll("*")].find((element) => element.__vue_app__).__vue_app__.config.globalProperties.$pinia;
        const defs = pinia._s.get("nodeDef").nodeDefsByName;
        const fact = (def) => ({ source: def.nodeSource.displayText, module: def.python_module });
        return { note: fact(defs.DiceForgeWildcardNote), other: fact(defs.DiceForgeRandomInt), description: defs.DiceForgeWildcardNote.description };
      });
      expect(facts.note).toEqual(facts.other);
      expect(facts.description).toContain("Save to WildCard");
      if (vue) await expect(nodeElement(page, id)).toContainText(facts.other.source); // The source badge under the node.
    });

    test("Wildcard Note's text has the prompt tools: __ suggests wildcards, and the node menu has the Wildcard Browser", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeWildcardNote", pos: [300, 60] }]);
      expect(await menuItems(page, id, "DiceForge.Wildcards")).toEqual(["📖 Syntax guide", "🎲 Wildcard Browser", "✂ Selection → new wildcard…"]);
      expect(await menuItems(page, id, "DiceForge.WildcardNote")).toEqual(["↻ Refresh the file list"]);
      const field = vue ? nodeElement(page, id).locator("textarea").first() : page.locator(`[data-e2e="${id}-text"]`);
      if (!vue) await page.evaluate((id) => window.app.graph.getNodeById(id).widgets.find((widget) => widget.name === "text").inputEl.setAttribute("data-e2e", `${id}-text`), id);
      await field.click();
      await page.keyboard.type("__hair/st");
      await expect(page.locator(".dfwc-pop")).toContainText("__hair/style__");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "text")).toBe("__hair/style__");
    });

    test("Wildcard Browser favorites: ☆ stars a file, ★ Favorites shows only them, the autocomplete puts them first", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      await page.locator(".dfwc button.open-all").click();
      const style = page.locator('.dfwc .row[data-name="hair/style"]');
      await style.locator("button.fav").click();
      await expect(style.locator("button.fav")).toHaveText("★");
      await page.locator(".dfwc button.close-all").click();
      await page.locator(".dfwc button.only-favorites").click(); // Only favorites, in open folders.
      await expect(page.locator(".dfwc .tree .row[data-name]")).toHaveCount(1);
      await expect(style).toBeVisible();
      await page.locator(".dfwc button.only-favorites").click();
      await expect(page.locator('.dfwc .row[data-name="color"]')).toBeVisible();
      await page.keyboard.press("Escape");
      const field = await promptField(page, id, "positive");
      await field.click();
      await page.keyboard.type("__hair/");
      await expect(page.locator(".dfwc-pop div").first()).toHaveText("★ __hair/style__2"); // Before hair/color, though c comes before s.
      await page.keyboard.press("Escape");
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      await page.locator(".dfwc button.only-favorites").click();
      await page.locator('.dfwc .row[data-name="hair/style"] button.fav').click(); // Unstarred: the favorites list is empty.
      await expect(page.locator(".dfwc .tree")).toContainText("No favorites yet");
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser converts a folder of txt files to yaml and back, and gives a yaml card its picture", async ({ page }) => {
      const pack = `CONV_${vue ? "vue" : "classic"}`; // A folder of its own: the tests share the server's files.
      const file = (...parts) => basePath("models", "wildcards", ...parts);
      writeFile(`models/wildcards/${pack}/sitting.txt`, "sitting\n");
      writeFile(`models/wildcards/${pack}/standing.txt`, "standing\nstanding, arms crossed\n");
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60], widgets: { positive: "1girl" } }]);
      await answerQuestions(page);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      await wildcardMode(dialog, "lines"); // Start in lines.
      const folder = dialog.locator(`.folder[data-path="${pack}"] > .row`), yamlRow = dialog.locator(`.row[data-name="${pack}.yaml"]`);
      const menu = page.locator(".df-menu");
      await folder.click({ button: "right" }); // Right-click: the folder's menu.
      await expect(menu.locator("button")).toContainText(["＋ Add", "🎲 Preview picks", "the folder", "＋ New file here…", "⇩ Export zip", "→ yaml"]);
      await menu.locator("button", { hasText: "→ yaml" }).click();
      await expect(dialog.locator(".status")).toContainText("Converted 2 wildcards into");
      expect(fs.existsSync(file(`${pack}.yaml`))).toBe(true);
      expect(fs.existsSync(file(pack, "sitting.txt"))).toBe(false);
      await expect(folder).toHaveCount(0); // The yaml file, whole: a row of its own, not a folder.
      await yamlRow.locator("button.more").click(); // ⋯ opens its menu.
      await expect(menu.locator("button", { hasText: /^→/ })).toHaveText(["→ txt files"]); // The same names, now from the yaml file.
      await page.keyboard.press("Escape"); // Closes the menu only.
      await expect(menu).toHaveCount(0);
      await expect(dialog).toHaveCount(1);
      await dialog.locator("button.mode").click(); // Cards: a picture for a card.
      await yamlRow.locator(".name").click();
      const sitting = dialog.locator(".card", { hasText: "sitting" });
      const chooser = page.waitForEvent("filechooser");
      await sitting.locator("button.picture").click();
      await (await chooser).setFiles({ name: "sitting.png", mimeType: "image/png", buffer: png(20, 30, [200, 50, 50]) });
      await expect(sitting.locator("img")).toHaveJSProperty("naturalWidth", 20);
      expect(fs.existsSync(file(pack, "sitting.png"))).toBe(true); // Next to the yaml file, where card packs keep them.
      await sitting.locator("button.no-picture").click();
      await expect(sitting.locator("img")).toHaveCount(0);
      expect(fs.existsSync(file(pack, "sitting.png"))).toBe(false);
      await dialog.locator("button.mode").click(); // Back to lines, and back to txt files.
      await yamlRow.click({ button: "right" });
      await menu.locator("button", { hasText: "→ txt files" }).click();
      await expect(dialog.locator(".status")).toContainText(`${pack}.yaml into 2 txt files`);
      expect(fs.readFileSync(file(pack, "standing.txt"), "utf8")).toBe("standing\nstanding, arms crossed\n");
      expect(fs.existsSync(file(`${pack}.yaml`))).toBe(false);
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser's editor has the autocomplete: wildcards and LoRAs while typing, Escape closes only the list", async ({ page }) => {
      const file = `complete_${vue ? "vue" : "classic"}`; // A file of its own: the tests share the server's files.
      writeFile(`models/wildcards/${file}.txt`, "one\n");
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      await wildcardMode(dialog, "lines"); // Lines: the editor.
      await dialog.locator(".row", { hasText: file }).locator(".name").click();
      const editor = dialog.locator(".edit textarea");
      await expect(editor).toHaveValue("one");
      await editor.press("Control+End");
      await page.keyboard.type("\ntwo __hair/st");
      await expect(page.locator(".dfwc-pop div").first()).toContainText("__hair/style__");
      await expect(page.locator(".dfwc-pop")).not.toContainText("Browse wildcards"); // The browser is open already.
      await page.keyboard.press("Enter");
      await expect(editor).toHaveValue("one\ntwo __hair/style__");
      await expect(dialog.locator("button.save")).toHaveText("Save •"); // An unsaved change, as when typed.
      await page.keyboard.type(", <lora:in");
      await expect(page.locator(".dfwc-pop div").first()).toContainText("style/ink");
      await page.keyboard.press("Escape"); // Closes the list, not the browser.
      await expect(page.locator(".dfwc-pop")).toHaveCount(0);
      await expect(dialog).toBeVisible();
      await page.keyboard.type("k");
      await page.keyboard.press("Tab");
      await expect(editor).toHaveValue("one\ntwo __hair/style__, <lora:style/ink:1>");
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser imports a zip card pack, finds wildcards by their lines, and + puts a line in the prompt", async ({ page }) => {
      const pack = `ZIP_${vue ? "vue" : "classic"}`; // A pack of its own: the tests share the server's files.
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60], widgets: { positive: "1girl" } }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      await wildcardMode(dialog, "lines"); // Lines: the editor.
      const chooser = page.waitForEvent("filechooser");
      await dialog.locator("button.import").click();
      await (await chooser).setFiles({ name: `${pack}.zip`, mimeType: "application/zip", buffer: zip({
        [`${pack}.yaml`]: `${pack}:\n  sitting: sitting, hands on lap\n  standing: standing\n`, [`${pack}/sitting.png`]: png(20, 30, [90, 60, 160]),
        [`${pack}/notes.pdf`]: "%PDF", [`${pack}/lines.txt`]: "# a comment\n3::quiet zebra pose\nloud pose\n" }) });
      await expect(dialog.locator(".status")).toHaveText(`Imported 3 files from ${pack}.zip; 1 not wildcards or pictures, left out.`);
      expect(fs.existsSync(basePath("models", "wildcards", pack, "sitting.png"))).toBe(true);
      await dialog.locator("input").first().fill("zebra"); // In no name: found by a line.
      const found = dialog.locator(`.row[data-name="${pack}/lines"]`); // Its own pack's (the other design's pack has the line too).
      await expect(found.locator(".found")).toHaveText("“3::quiet zebra pose”");
      await found.locator(".name").click();
      await expect(dialog.locator(".edit textarea")).toHaveValue("# a comment\n3::quiet zebra pose\nloud pose");
      const code = dialog.locator(".code");
      const box = await code.boundingBox();
      await page.mouse.move(box.x + 60, box.y + 6 + 20 * 1 + 10); // Over the second line.
      await code.locator("button.line-add").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, quiet zebra pose"); // Without its weight.
      await page.mouse.move(box.x + 60, box.y + 6 + 10); // The comment line: nothing to add.
      await expect(code.locator("button.line-add")).toBeHidden();
      await found.click({ button: "right" }); // 🎲 Preview picks: what runs would put in for it.
      await page.locator(".df-menu button", { hasText: "🎲 Preview picks" }).click();
      const picks = dialog.locator(".picks .pick .text");
      await expect(picks).toHaveCount(5);
      for (const text of await picks.allTextContents()) expect(["quiet zebra pose", "loud pose"]).toContain(text); // Weights and all, not the comment.
      await dialog.locator(".picks .pick").first().locator("button.add").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toMatch(/^1girl, quiet zebra pose, (quiet zebra|loud) pose$/);
      await dialog.locator(".picks button.close-picks").click();
      await expect(dialog.locator(".picks")).toBeHidden();
      const again = page.waitForEvent("filechooser"); // The same zip again: what is there is kept.
      await dialog.locator("button.import").click();
      await (await again).setFiles({ name: `${pack}.zip`, mimeType: "application/zip", buffer: zip({ [`${pack}.yaml`]: "changed: [x]\n" }) });
      await expect(dialog.locator(".status")).toHaveText(`Imported 0 files from ${pack}.zip; 1 already there, kept as they were.`);
      const download = page.waitForEvent("download"); // ⇩ zip on the folder: the pack again, its yaml file too.
      await dialog.locator(`.folder[data-path="${pack}"] > .row`).click({ button: "right" });
      await page.locator(".df-menu button", { hasText: "⇩ Export zip" }).click();
      const file = await download;
      expect(file.suggestedFilename()).toBe(`wildcards-${pack}.zip`);
      const listed = fs.readFileSync(await file.path()).toString("latin1"); // A zip lists its file names as they are.
      for (const name of [`${pack}.yaml`, `${pack}/sitting.png`, `${pack}/lines.txt`]) expect(listed).toContain(name);
      expect(listed).not.toContain("notes.pdf");
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser creates, renames and deletes files", async ({ page }) => {
      const tag = vue ? "vue" : "classic", wildcards = (...parts) => basePath("models", "wildcards", ...parts);
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const answers = [`crud_${tag}/new`, `crud_${tag}/new`, `crud_${tag}_done/renamed`]; // The prompts in order: new file, the same name again, rename.
      await answerQuestions(page, ({ prompt }) => (prompt ? answers.shift() : true));
      const editor = page.locator(".dfwc .edit textarea"), save = page.locator(".dfwc button.save"), status = page.locator(".dfwc .status");
      await page.locator(".dfwc button", { hasText: "+ New file" }).click();
      await expect(page.locator(".dfwc .row.sel")).toContainText("new");
      await editor.fill("alpha\nbeta");
      await expect(save).toHaveText("Save •"); // Unsaved changes are marked...
      await editor.press("Control+s");
      await expect(status).toContainText(`Saved crud_${tag}/new.txt`);
      await expect(save).toHaveText("Save"); // ...until saved (Ctrl+S here).
      expect(fs.readFileSync(wildcards(`crud_${tag}`, "new.txt"), "utf8")).toBe("alpha\nbeta\n");
      await page.locator(".dfwc button", { hasText: "+ New file" }).click(); // A taken name: refused, the file keeps its lines.
      await expect(status).toContainText("already exists");
      expect(fs.readFileSync(wildcards(`crud_${tag}`, "new.txt"), "utf8")).toBe("alpha\nbeta\n");
      await page.locator(".dfwc button.rename").click();
      await expect(status).toContainText(`Renamed crud_${tag}/new to crud_${tag}_done/renamed`);
      await expect(page.locator(".dfwc .row.sel")).toContainText("renamed");
      await expect(editor).toHaveValue("alpha\nbeta");
      await status.locator("button.undo").click(); // ↶ Undo: the old name back, and again the new one.
      await expect(status).toContainText(`Renamed crud_${tag}_done/renamed to crud_${tag}/new`);
      await status.locator("button.undo").click();
      await expect(status).toContainText(`Renamed crud_${tag}/new to crud_${tag}_done/renamed`);
      expect(fs.existsSync(wildcards(`crud_${tag}`))).toBe(false);
      await page.locator(".dfwc button.delete").click();
      await expect(status).toContainText(`Deleted crud_${tag}_done/renamed.txt`);
      await status.locator("button.undo").click(); // ↶ Undo the delete: back, and open.
      await expect(status).toContainText(`crud_${tag}_done/renamed is back.`);
      await expect(editor).toHaveValue("alpha\nbeta");
      expect(fs.readFileSync(wildcards(`crud_${tag}_done`, "renamed.txt"), "utf8")).toBe("alpha\nbeta\n");
      await page.locator(".dfwc button.delete").click();
      await expect(status).toContainText(`Deleted crud_${tag}_done/renamed.txt`);
      expect(fs.existsSync(wildcards(`crud_${tag}_done`))).toBe(false);
      await expect(page.locator(".dfwc .row", { hasText: `crud_${tag}` })).toHaveCount(0);
      await expect(page.locator(".dfwc button.delete")).toBeDisabled();
      await page.locator(".dfwc button.open-all").click(); // The yaml wildcards are in closed folders.
      await page.locator('.dfwc .row[data-name="pack.yaml"] .name').click(); // A yaml file opens whole; its keys are renamed in its text.
      await expect(page.locator(".dfwc .edit textarea")).toHaveValue(/^characters:/);
      await expect(page.locator(".dfwc button.rename")).toBeDisabled();
      await expect(page.locator(".dfwc button.delete")).toBeEnabled();
    });

    test("Wildcard Browser shows a yaml file whole: one row in its folder, its text as written, + on a line, saved with its comments, deleted and back", async ({ page }) => {
      const pack = `YFILE_${vue ? "vue" : "classic"}`, file = basePath("models", "wildcards", "packs", `${pack}.yaml`);
      const text = `# my poses\n${pack}:\n  sitting: [sitting, on a chair]\n  standing: standing,`;
      writeFile(`models/wildcards/packs/${pack}.yaml`, `${text}\n`);
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60], widgets: { positive: "1girl" } }]);
      await answerQuestions(page, ({ prompt }) => (prompt ? `packs/${pack}/lying` : true));
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc"), editor = dialog.locator(".edit textarea"), status = dialog.locator(".status");
      await wildcardMode(dialog, "lines"); // Lines.
      await dialog.locator("button.open-all").click();
      const row = dialog.locator(`.row[data-name="packs/${pack}.yaml"]`);
      await expect(row).toContainText(`📜 ${pack}.yaml`);
      await expect(row).toContainText("yaml · 2 wildcards");
      await expect(dialog.locator(`.row[data-name="packs/${pack}/sitting"]`)).toHaveCount(0); // Its wildcards are in it, not rows of their own,
      await expect(dialog.locator(`.folder[data-path="packs/${pack}"]`)).toHaveCount(0); // nor folders.
      await row.locator(".name").click();
      await expect(editor).toHaveValue(text);
      await expect(dialog.locator("button.rename")).toBeDisabled(); // Its keys are renamed in its text.
      const code = dialog.locator(".code"), box = await code.boundingBox();
      await page.mouse.move(box.x + 60, box.y + 6 + 20 * 3 + 10); // + on "standing: standing,": the option, not the key.
      await code.locator("button.line-add").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, standing,");
      for (const line of [1, 2]) { // The key of keys, and a [list] on one line: nothing to add.
        await page.mouse.move(box.x + 60, box.y + 6 + 20 * line + 10);
        await expect(code.locator("button.line-add")).toBeHidden();
      }
      await editor.fill(`${text}\n  # kneeling, new\n  kneeling: kneeling,`);
      await editor.press("Control+s");
      await expect(status).toContainText(`Saved packs/${pack}.yaml.`);
      expect(fs.readFileSync(file, "utf8")).toBe(`${text}\n  # kneeling, new\n  kneeling: kneeling,\n`); // As written, comments and all.
      await expect(row).toContainText("yaml · 3 wildcards");
      await editor.fill(`${pack}:\n  broken: [x`); // Not yaml: not saved.
      await editor.press("Control+s");
      await expect(status).toContainText("not valid yaml");
      expect(fs.readFileSync(file, "utf8")).toContain("kneeling: kneeling,");
      await row.click({ button: "right" });
      await page.locator(".df-menu button", { hasText: "Delete the file" }).click();
      await expect(status).toContainText(`Deleted packs/${pack}.yaml.`);
      expect(fs.existsSync(file)).toBe(false);
      await status.locator("button.undo").click();
      await expect(status).toContainText(`packs/${pack}.yaml is back.`);
      await expect(editor).toHaveValue(`${text}\n  # kneeling, new\n  kneeling: kneeling,`);
      await row.click({ button: "right" }); // A new wildcard in it: the file opens on its line.
      await page.locator(".df-menu button", { hasText: "New wildcard in it" }).click();
      await expect(status).toContainText(`Added __packs/${pack}/lying__ to ${pack}.yaml.`);
      await expect(editor).toHaveValue(/ {2}lying: \[\]$/);
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser cards: the tree shows a yaml file whole, its row shows its cards; a folder shows all of its files' cards", async ({ page }) => {
      const pack = `YTREE_${vue ? "vue" : "classic"}`;
      writeFile(`models/wildcards/${pack}/poses.yaml`, `POSES:\n  sitting: sitting,\n  standing: standing,\n`);
      writeFile(`models/wildcards/${pack}/colors.txt`, "red\nblue\n");
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60], widgets: { positive: "1girl" } }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      await wildcardMode(dialog, "cards"); // Cards.
      await dialog.locator(".top input").first().fill(pack);
      await expect(dialog.locator(`.folder[data-path="${pack}/POSES"]`)).toHaveCount(0); // No folder of its keys.
      const row = dialog.locator(`.row[data-name="${pack}/poses.yaml"]`);
      await row.locator(".name").click();
      await expect(row).toHaveClass(/sel/);
      await expect(dialog.locator(".cards-head b")).toHaveText(`📜 ${pack}/poses.yaml`);
      await expect(dialog.locator(".card .title")).toHaveText(["sitting", "standing"]);
      await dialog.locator(".cards-head button.random").click(); // The cards' own folder: __pack/POSES/*__.
      await expect.poll(() => widgetValue(page, id, "positive")).toBe(`1girl, __${pack}/POSES/*__`);
      await dialog.locator(`.folder[data-path="${pack}"] > .row .name`).click(); // The folder: the yaml file's cards and the txt file's.
      await expect(dialog.locator(".cards-head b")).toHaveText(`📁 ${pack}`);
      await expect(dialog.locator(".card .title")).toHaveText(["colors", "sitting", "standing"]);
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser asks before another file takes the place of unsaved changes", async ({ page }) => {
      const top = `wdrop_${vue ? "vue" : "classic"}`;
      writeFile(`models/wildcards/${top}/a.txt`, "a\n");
      writeFile(`models/wildcards/${top}/b.txt`, "b\n");
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      const answers = [false, true];
      await answerQuestions(page, () => answers.shift());
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc"), editor = dialog.locator(".edit textarea");
      await wildcardMode(dialog, "lines"); // Lines.
      await dialog.locator(".top input").first().fill(top);
      await dialog.locator(`.row[data-name="${top}/a"] .name`).click();
      await expect(editor).toHaveValue("a");
      await editor.fill("a\nunsaved");
      await dialog.locator(`.row[data-name="${top}/b"] .name`).click(); // Asked: no, and a stays open with its changes;
      await expect(editor).toHaveValue("a\nunsaved");
      await dialog.locator(`.row[data-name="${top}/b"] .name`).click(); // yes, and b opens.
      await expect(editor).toHaveValue("b");
      expect(answers).toEqual([]);
      expect(fs.readFileSync(basePath("models", "wildcards", top, "a.txt"), "utf8")).toBe("a\n");
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser cards: a card isn't changed while its yaml file has unsaved changes in the lines view, which then shows the change", async ({ page }) => {
      const pack = `YBUSY_${vue ? "vue" : "classic"}`, text = `${pack}:\n  a: a,\n  b: b,`;
      writeFile(`models/wildcards/${pack}.yaml`, `${text}\n`);
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc"), editor = dialog.locator(".edit textarea"), mode = dialog.locator("button.mode");
      const row = dialog.locator(`.row[data-name="${pack}.yaml"]`), card = dialog.locator(`.card[data-name="${pack}/a"]`);
      if (await mode.textContent() === "📄 Lines") await mode.click(); // Lines.
      await dialog.locator(".top input").first().fill(pack);
      await row.locator(".name").click();
      await expect(editor).toHaveValue(text);
      await editor.fill(`${text}\n  c: c,`); // Unsaved there,
      await mode.click();
      await row.locator(".name").click();
      await card.locator("button.edit-card").click(); // so the card isn't edited:
      await expect(dialog.locator(".status")).toContainText(`${pack}.yaml is open in the lines view with unsaved changes`);
      await expect(dialog.locator(".card-edit")).toHaveCount(0);
      await mode.click();
      await editor.fill(text); // Undone there,
      await mode.click();
      await card.locator("button.edit-card").click(); // so the card is edited,
      await card.locator(".card-edit textarea").fill("a, changed");
      await card.locator("button.save-card").click();
      await expect(dialog.locator(".status")).toContainText(`Saved __${pack}/a__ in ${pack}.yaml.`);
      await mode.click();
      await expect(editor).toHaveValue(`${pack}:\n  a: a, changed\n  b: b,`); // and the lines view shows it.
      await expect(dialog.locator("button.save")).toHaveText("Save");
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser cards: 🖊 edits a card's lines on the card, ＋ New card goes into the folder's yaml file, ⋯ renames and deletes a card", async ({ page }) => {
      const pack = `CCRUD_${vue ? "vue" : "classic"}`, file = basePath("models", "wildcards", `${pack}.yaml`);
      writeFile(`models/wildcards/${pack}.yaml`, `${pack}:\n  sitting: sitting,\n`);
      writeFile(`models/wildcards/${pack}/sitting.png`, png(30, 40, [200, 80, 80]));
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      const answers = [`${pack}/kneeling`, `${pack}/seated`]; // The prompts in order: the new card, the rename.
      await answerQuestions(page, ({ prompt }) => (prompt ? answers.shift() : true));
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc"), status = dialog.locator(".status");
      await wildcardMode(dialog, "cards"); // Cards.
      await dialog.locator(`.row[data-name="${pack}.yaml"] .name`).click(); // The yaml file's cards.
      const card = (name) => dialog.locator(`.card[data-name="${pack}/${name}"]`);
      await card("sitting").locator("button.edit-card").click();
      const lines = card("sitting").locator(".card-edit textarea");
      await expect(lines).toHaveValue("sitting,");
      await lines.fill("sitting,\non a chair");
      await lines.press("Control+s");
      await expect(status).toContainText(`Saved __${pack}/sitting__ in ${pack}.yaml`);
      await expect(card("sitting")).toHaveCount(2); // Two lines now: a card for each (🂠 Card per line),
      await dialog.locator(".cards-head button.line-cards").click();
      await expect(card("sitting")).toHaveCount(1); // or one for the key.
      await expect(card("sitting").locator(".line")).toHaveText("2 lines: sitting, · on a chair");
      await dialog.locator(".cards-head button.new-card").click();
      await expect(status).toContainText(`Added __${pack}/kneeling__ to ${pack}.yaml`);
      const fresh = card("kneeling").locator(".card-edit textarea");
      await expect(fresh).toBeFocused(); // Its lines next.
      await fresh.fill("kneeling,");
      await card("kneeling").locator("button.save-card").click();
      await expect.poll(() => fs.readFileSync(file, "utf8")).toContain("  kneeling: kneeling,\n"); // One line: key: text.
      await card("sitting").locator(".title-row button.more").click();
      await page.locator(".df-menu button", { hasText: "Rename" }).click();
      await expect(status).toContainText(`Renamed ${pack}/sitting to ${pack}/seated`);
      await expect(card("seated").locator("img")).toHaveJSProperty("naturalWidth", 30); // Its picture went along.
      expect(fs.existsSync(basePath("models", "wildcards", pack, "seated.png"))).toBe(true);
      await card("seated").click({ button: "right" });
      await page.locator(".df-menu button", { hasText: "Delete" }).click();
      await expect(status).toContainText(`Deleted __${pack}/seated__ from ${pack}.yaml`);
      await expect(card("seated")).toHaveCount(0);
      await status.locator("button.undo").click();
      await expect(card("seated").locator("img")).toHaveJSProperty("naturalWidth", 30); // Back, with its picture.
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser cards: 🂠 a card per line of a yaml card, each with its own picture, + Add puts in the line", async ({ page }) => {
      const pack = `LINES_${vue ? "vue" : "classic"}`;
      writeFile(`models/wildcards/${pack}.yaml`, `${pack}:\n  standing: [standing, "2::hands on hips", arms crossed]\n  sitting: sitting,\n`);
      writeFile(`models/wildcards/cards/${pack}/standing/[0].png`, png(30, 40, [80, 80, 200])); // Where the A1111 Wildcard Gallery's packs keep it.
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60], widgets: { positive: "1girl" } }]);
      await answerQuestions(page);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      await wildcardMode(dialog, "cards"); // Cards.
      await dialog.locator(`.row[data-name="${pack}.yaml"] .name`).click(); // The yaml file's cards.
      const lines = dialog.locator(`.card.line-card[data-name="${pack}/standing"]`);
      await expect(lines.locator(".title")).toHaveText(["standing · 1/3", "standing · 2/3", "standing · 3/3"]);
      await expect(lines.nth(0).locator("img")).toHaveJSProperty("naturalWidth", 30);
      await expect(dialog.locator(`.card[data-name="${pack}/sitting"]:not(.line-card)`)).toHaveCount(1); // One line: the card itself.
      const chooser = page.waitForEvent("filechooser");
      await lines.nth(2).locator("button.picture").click();
      await (await chooser).setFiles({ name: "crossed.png", mimeType: "image/png", buffer: png(20, 30, [200, 50, 50]) });
      await expect(lines.nth(2).locator("img")).toHaveJSProperty("naturalWidth", 20);
      expect(fs.existsSync(basePath("models", "wildcards", pack, "standing", "[2].png"))).toBe(true); // Next to the yaml file.
      await lines.nth(1).locator("button.add").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, hands on hips"); // The line, without its weight.
      await lines.nth(2).locator("button.no-picture").click();
      await expect(lines.nth(2).locator("img")).toHaveCount(0);
      await dialog.locator(".cards-head button.line-cards").click(); // One card for the key again.
      await expect(dialog.locator(`.card[data-name="${pack}/standing"]`)).toHaveCount(1);
      await page.keyboard.press("Escape");
    });

    test("Wildcards to Text has the prompt tools in its text field: highlighting, the menu's browsers and guide", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeWildcardsToText", pos: [300, 60], widgets: { text: "a __color__ car" } }]);
      const menu = await page.evaluate((id) => window.app.extensions.flatMap((extension) => extension.getNodeMenuItems?.(window.app.graph.getNodeById(id)) ?? [])
        .filter(Boolean).map((item) => item.content), id);
      expect(menu).toEqual(expect.arrayContaining(["📖 Syntax guide", "🎲 Wildcard Browser", "🏷 Tag Browser"]));
      expect(menu).not.toContain("🎨 Prompt styles"); // Styles have a negative part: CLIP Dual Text Encode only.
      await expect.poll(() => page.evaluate((id) => !!document.querySelector(".dfhl-input") && window.app.graph.getNodeById(id).widgets.some((widget) => widget.name === "text"), id)).toBe(true);
      await clickMenu(page, id, "DiceForge.Wildcards", "Syntax guide");
      await page.locator(".dfsg input").fill("lock");
      await page.locator(".dfsg .row button").click();
      await expect.poll(() => widgetValue(page, id, "text")).toBe("a __color__ car, {sky|!sea|forest}"); // Into its text field.
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser cards: a yaml card pack's keys with their pictures, + Add a card or a random one", async ({ page }) => {
      const pack = `CARDS_${vue ? "vue" : "classic"}`; // A pack of its own: the tests share the server's files.
      writeFile(`models/wildcards/${pack}.yaml`, `${pack}:\n  sitting: sitting,\n  standing: standing,\n  bare: no picture here,\n`);
      writeFile(`models/wildcards/${pack}/sitting.png`, png(30, 40, [200, 80, 80]));
      writeFile(`models/wildcards/${pack}/standing.png`, png(30, 40, [80, 80, 200]));
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60], widgets: { positive: "1girl" } }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      await wildcardMode(dialog, "lines"); // Start in lines.
      await expect(dialog.locator("button.mode")).toHaveText("🃏 Cards");
      await dialog.locator("button.mode").click();
      await dialog.locator(`.row[data-name="${pack}.yaml"] .name`).click(); // The yaml file's cards.
      await expect(dialog.locator(".cards-head b")).toHaveText(`📜 ${pack}.yaml`);
      const cards = dialog.locator(".card");
      await expect(cards).toHaveCount(3);
      await expect(cards.filter({ hasText: "sitting" }).locator("img")).toHaveJSProperty("naturalWidth", 30); // Its picture, POSES/sitting.png-style.
      await expect(cards.filter({ hasText: "bare" }).locator(".pic .none")).toHaveText("no picture here,"); // No picture: its text.
      await expect(dialog.locator(".edit")).toBeHidden();
      await cards.filter({ hasText: "standing" }).locator("button.add").click();
      await dialog.locator(".cards-head button.random").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toBe(`1girl, __${pack}/standing__, __${pack}/*__`);
      await dialog.locator("button.mode").click(); // Back to lines (remembered for the next time).
      await expect(dialog.locator(".edit")).toBeVisible();
      await page.keyboard.press("Escape");
    });

    test("Syntax guide: the prompt syntax by topic, searched, an example inserted into the prompt", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60], widgets: { positive: "1girl" } }]);
      const menu = await page.evaluate((id) => window.app.extensions.flatMap((extension) => extension.getNodeMenuItems?.(window.app.graph.getNodeById(id)) ?? [])
        .filter(Boolean).map((item) => item.content), id);
      expect(menu[0]).toBe("📖 Syntax guide"); // First in the node's menu.
      await clickMenu(page, id, "DiceForge.Wildcards", "Syntax guide");
      const guide = page.locator(".dfsg");
      await expect(guide.locator("h3")).toHaveText(["Wildcards", "Choices", "Variables", "LoRAs and weights", "Comments and escapes", "Wildcard files"]);
      await guide.locator("input").fill("lock");
      await expect(guide.locator(".row")).toHaveCount(1);
      await guide.locator(".row button").click();
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, {sky|!sea|forest}");
      await expect(guide.locator(".status")).toHaveText("Inserted into the positive prompt.");
      await page.keyboard.press("Escape");
      await expect(guide).toHaveCount(0);
      await clickMenu(page, id, "DiceForge.Wildcards", "Syntax guide");
      await expect(guide.locator("input")).toHaveValue("lock"); // Opens where it was closed.
      await guide.locator("h2").click();
      await page.keyboard.press("?"); // Its keys; Escape closes only them.
      await expect(page.locator(".df-keys h3")).toHaveText("⌨ Prompt syntax");
      await page.keyboard.press("Escape");
      await expect(page.locator(".df-keys")).toHaveCount(0);
      await expect(guide).toHaveCount(1);
      await expect(guide.locator(".row")).toHaveCount(1);
      const size = () => guide.evaluate((element) => [element.offsetWidth, element.offsetHeight]);
      await guide.evaluate((element) => { element.style.width = "640px"; element.style.height = "480px"; }); // As dragging its corner leaves it.
      await expect.poll(() => page.evaluate(() => localStorage.getItem("diceforge.window.size.syntax"))).toBe('{"width":640,"height":480}');
      await page.keyboard.press("Escape");
      await clickMenu(page, id, "DiceForge.Wildcards", "Syntax guide");
      expect(await size()).toEqual([640, 480]); // The same size again.
      await guide.locator("h2").dblclick(); // Its default size.
      expect((await size())[0]).toBeGreaterThan(640);
      await page.keyboard.press("Escape");
    });

    test("Prompt styles: the family's quality tags in and out with a click, Auto from the connected model, your own saved and deleted", async ({ page, request }) => {
      await lookUp(request, "checkpoints", "illustrious_base.safetensors");
      const [checkpoint, encode] = await addNodes(page, [
        { type: "CheckpointLoaderSimple", widgets: { ckpt_name: "illustrious_base.safetensors" } },
        { type: "DiceForgeCLIPDualTextEncode", pos: [460, 40], widgets: { positive: "1girl, smile", negative: "" } },
      ]);
      const items = () => page.evaluate((id) => window.app.extensions.find((item) => item.name === "DiceForge.PromptStyles")
        .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options.filter(Boolean).map((item) => item.content), encode);
      const click = (content) => page.evaluate(([id, content]) => window.app.extensions.find((item) => item.name === "DiceForge.PromptStyles")
        .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options.find((item) => item?.content.includes(content)).callback(), [encode, content]);
      const prompts = () => Promise.all([widgetValue(page, encode, "positive"), widgetValue(page, encode, "negative")]);
      await expect.poll(items).toContain("🎨 Illustrious quality");
      await click("Illustrious quality");
      expect(await prompts()).toEqual(["masterpiece, best quality, amazing quality, very aesthetic, absurdres, 1girl, smile",
        "lowres, worst quality, bad quality, bad anatomy, bad hands, jpeg artifacts, signature, watermark, text"]);
      expect(await items()).toContain("✓ Illustrious quality");
      await click("Illustrious quality"); // Again: taken out.
      expect(await prompts()).toEqual(["1girl, smile", ""]);
      await click("Auto"); // Nothing on the model input yet.
      expect(await prompts()).toEqual(["1girl, smile", ""]);
      await connect(page, checkpoint, 0, encode, "model");
      await click("Auto");
      await expect.poll(prompts).toEqual(["masterpiece, best quality, amazing quality, very aesthetic, absurdres, 1girl, smile",
        "lowres, worst quality, bad quality, bad anatomy, bad hands, jpeg artifacts, signature, watermark, text"]);
      // Your own: the prompts as they are, saved under a name, then put into other prompts, then deleted.
      await setWidget(page, encode, "positive", "{prompt}, film grain");
      await setWidget(page, encode, "negative", "cartoon");
      await answerQuestions(page, ({ prompt }) => (prompt ? `E2E film ${vue}` : true));
      await click("Save the prompts as a style");
      await expect.poll(items).toContain(`✓ E2E film ${vue}`); // Saved from these prompts: they have it.
      await setWidget(page, encode, "positive", "a cat");
      await setWidget(page, encode, "negative", "");
      await expect.poll(items).toContain(`★ E2E film ${vue}`); // Other prompts: your style (★), not in them.
      await click(`★ E2E film ${vue}`);
      expect(await prompts()).toEqual(["a cat, film grain", "cartoon"]);
      await click(`🗑 Delete E2E film ${vue}`);
      await expect.poll(items).not.toContain(`🗑 Delete E2E film ${vue}`);
      expect((await (await request.get("/diceforge/styles")).json()).user.map((style) => style.name)).not.toContain(`E2E film ${vue}`);
    });

    test("Tag autocomplete: the Danbooru list downloaded from the node's menu, then the most used tags while a word is typed", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeCLIPDualTextEncode", pos: [300, 60] }]);
      const menu = () => page.evaluate((id) => window.app.extensions.find((item) => item.name === "DiceForge.TagAutocomplete")
        .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options.map((item) => item.content), id);
      await expect.poll(menu).toContain("⬇ Download: Danbooru (anime: Illustrious, NoobAI, Anima, Pony)");
      await page.evaluate((id) => window.app.extensions.find((item) => item.name === "DiceForge.TagAutocomplete")
        .getNodeMenuItems(window.app.graph.getNodeById(id))[0].submenu.options[0].callback(), id);
      await expect.poll(menu).toContain("✓ Download again: Danbooru (anime: Illustrious, NoobAI, Anima, Pony)");
      try {
        const positive = await promptField(page, id, "positive");
        await positive.click();
        await page.keyboard.type("1gi");
        await expect(page.locator(".dfwc-pop div").first()).toContainText("1girl");
        await page.keyboard.press("Enter");
        await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, ");
        await page.keyboard.type("lo");
        await expect(page.locator(".dfwc-pop div")).toHaveText([/long_hair\s*5M/, /long_sleeves\s*1\.5M/]); // Most used first, with the count.
        await page.keyboard.press("Enter");
        await expect.poll(() => widgetValue(page, id, "positive")).toBe("1girl, long hair, "); // Spaces for underscores.
        await page.keyboard.type("mik");
        await expect(page.locator(".dfwc-pop div").first()).toContainText("miku → hatsune_miku"); // By its alias.
        await page.keyboard.press("Escape");
        await expect(page.locator(".dfwc-pop")).toHaveCount(0);
        // The Tag Browser: search, a type, + Add and − Neg, ★ favorites.
        await clickMenu(page, id, "DiceForge.TagBrowser", "Tag Browser");
        const browser = page.locator(".dftb");
        await expect(browser.locator(".row .name b")).toHaveText(["1girl", "long_hair", "smile", "long_sleeves", "hatsune_miku"]); // Most used first.
        await browser.locator(".top input").fill("long");
        await expect(browser.locator(".row .name b")).toHaveText(["long_hair", "long_sleeves"]);
        await expect(browser.locator(".row", { hasText: "long_sleeves" }).locator("a.wiki")).toHaveAttribute("href", "https://danbooru.donmai.us/wiki_pages/long_sleeves"); // ↗: the wiki.
        await browser.locator(".row", { hasText: "long_sleeves" }).locator("button.neg").click();
        await expect.poll(() => widgetValue(page, id, "negative")).toBe("long sleeves");
        await browser.locator(".top input").fill("");
        await browser.locator(".types button", { hasText: "Characters" }).click();
        await expect(browser.locator(".row .name b")).toHaveText(["hatsune_miku"]);
        await browser.locator(".row button.fav").click();
        await browser.locator(".types button", { hasText: "Favorites" }).click();
        await expect(browser.locator(".row .name b")).toHaveText(["hatsune_miku"]);
        await browser.locator(".row button.add").click();
        await expect(browser.locator(".status")).toContainText("Added hatsune miku to the");
        await page.keyboard.press("Escape");
        await expect(browser).toHaveCount(0);
        writeFile("user/DiceForge/tags/e621.csv", "fox_tail,0,9000,\n"); // An e621 tag: ↗ opens e621's wiki.
        await clickMenu(page, id, "DiceForge.TagBrowser", "Tag Browser");
        await expect(browser.locator(".types button.on")).toHaveText("★ Favorites"); // Opens where it was closed.
        await expect(browser.locator(".row .name b")).toHaveText(["hatsune_miku"]);
        await browser.locator(".types button", { hasText: "All" }).click();
        await browser.locator(".top input").fill("fox");
        await expect(browser.locator(".row .name b")).toHaveText(["fox_tail"]);
        await expect(browser.locator(".row a.wiki")).toHaveAttribute("href", "https://e621.net/wiki_pages/show_or_new?title=fox_tail");
        // The basket: tags picked across searches, put in all at once.
        await browser.locator(".row button.pick").click();
        await browser.locator(".top input").fill("long");
        await expect(browser.locator(".row .name b")).toHaveText(["long_hair", "long_sleeves"]);
        await browser.locator(".row", { hasText: "long_sleeves" }).locator("button.pick").click();
        await expect(browser.locator(".basket .count")).toHaveText("2 picked");
        await expect(browser.locator(".basket .tags")).toHaveText("fox tail, long sleeves");
        await expect(browser.locator('.row[data-tag="long_hair"] .has')).toHaveAttribute("title", "Already in the positive prompt"); // ✓: in a prompt.
        await expect(browser.locator('.row[data-tag="long_sleeves"] .has')).toHaveAttribute("title", "Already in the negative prompt");
        await browser.locator(".basket button.neg").click();
        await expect.poll(() => widgetValue(page, id, "negative")).toBe("long sleeves, hatsune miku, fox tail"); // + Add above followed the cursor there.
        await expect(browser.locator(".status")).toHaveText("Added 1 tag to the negative prompt. 1 was already there."); // Not twice.
        await expect(browser.locator(".basket")).toBeHidden();
        // 🔗 Related: what Danbooru finds most often with a tag; + puts one in.
        await browser.locator('.row[data-tag="long_hair"] button.related-open').click();
        await expect(browser.locator(".related .chip .pick-chip")).toHaveText(["☐ blue_eyes", "☐ hatsune_miku", "☐ smile"]);
        await browser.locator('.related .chip[data-tag="blue_eyes"] button.add').click();
        await expect.poll(() => widgetValue(page, id, "negative")).toBe("long sleeves, hatsune miku, fox tail, blue eyes");
        // The keyboard: ↑ ↓ to a tag, Enter (not twice), Shift+Enter to the negative prompt, Ctrl+Enter to the basket.
        await page.keyboard.press("/");
        await expect(browser.locator(".top input")).toBeFocused();
        await page.keyboard.press("ArrowDown");
        await page.keyboard.press("ArrowDown");
        await expect(browser.locator('.row[data-tag="long_sleeves"]')).toHaveClass(/cursor/);
        await page.keyboard.press("Enter");
        await expect(browser.locator(".status")).toHaveText("long sleeves is already in the negative prompt.");
        await page.keyboard.press("ArrowUp");
        await page.keyboard.press("Shift+Enter");
        await expect.poll(() => widgetValue(page, id, "negative")).toBe("long sleeves, hatsune miku, fox tail, blue eyes, long hair");
        await page.keyboard.press("Control+Enter");
        await expect(browser.locator(".basket .count")).toHaveText("1 picked");
        await page.keyboard.press("Escape");
      } finally {
        fs.rmSync(basePath("user", "DiceForge", "tags"), { recursive: true, force: true }); // No tag suggestions in the other tests.
        fs.rmSync(basePath("user", "DiceForge", "tag_favorites.json"), { force: true });
      }
    });

    test("a workflow queued from the page fills in the prompt", async ({ page, request }) => {
      const [encode, preview] = await addNodes(page, [
        { type: "DiceForgeCLIPDualTextEncode", widgets: { positive: "a __color__ car, {2$$__characters/*/outfit__}", seed: 3 } },
        { type: "PreviewAny", pos: [500, 40] },
      ]);
      await connect(page, encode, 3, preview, 0);
      await queueFromPage(page, request);
      const history = Object.values(await (await request.get("/history?max_items=1")).json())[0];
      const text = history.outputs[String(preview)].text[0];
      expect(text).toMatch(/^a (red|blue|green|white) car, [a-z ]+, [a-z ]+$/);
      // No panel of the last run under the inputs: the prompts as encoded go to the prompt history, with the seed they came from.
      expect(await page.evaluate((id) => window.app.graph.getNodeById(id).widgets.map((widget) => widget.name), encode)).not.toContain("prompt_preview");
      const kept = () => page.evaluate((id) => window.app.graph.getNodeById(id).properties.dice_forge_history, encode);
      expect((await kept())[0]).toMatchObject({ positive: text, seed: 3, seed_mode: "random" });
      await page.evaluate((id) => window.app.graph.getNodeById(id).onExecuted({ dice_forge_prompts: [{ positive: "a car", negative: "", seed: 1,
        seed_mode: "combinations", note: "combination 2 of 8" }] }), encode); // What the run notes (combination N of M, the LoRAs of tags) shows with its seed.
      await clickMenu(page, encode, "DiceForge.PromptPreview", "Prompt history");
      await expect(page.locator(".dfph .entry .when").first()).toContainText("seed 1 (combinations, combination 2 of 8)");
      await page.keyboard.press("Escape");
    });

    test("the prompt history keeps the last runs with their images: put back a seed, use a text, pin, remove", async ({ page, request }) => {
      const [encode, preview, image, show] = await addNodes(page, [
        { type: "DiceForgeCLIPDualTextEncode", widgets: { positive: "a {red|blue|green|white|black|pink} car", seed: 1, control_after_generate: "increment" } },
        { type: "PreviewAny", pos: [500, 40] },
        { type: "EmptyImage", pos: [40, 520], widgets: { width: 32, height: 32 } },
        { type: "PreviewImage", pos: [400, 520] },
      ]);
      await connect(page, encode, 3, preview, 0);
      await connect(page, image, 0, show, 0); // An image made in the same runs: kept with each run's prompts.
      for (let run = 0; run < 3; run++) {
        await setWidget(page, image, "color", run * 1000); // Another image each run.
        await queueFromPage(page, request); // Seeds 1, 2, 3.
      }
      const lastRun = () => page.evaluate((id) => window.app.graph.getNodeById(id).properties.dice_forge_history[0].positive, encode);
      const texts = (await page.evaluate((id) => window.app.graph.getNodeById(id).properties.dice_forge_history.map((item) => item.positive), encode)).reverse();
      await clickMenu(page, encode, "DiceForge.PromptPreview", "Prompt history");
      const dialog = page.locator(".dfph");
      await expect(dialog.locator(".top .muted")).toHaveText("3 runs, newest first");
      const entries = dialog.locator(".entry");
      await expect(entries.locator(".when")).toHaveText([/seed 3 \(random\)$/, /seed 2 \(random\)$/, /seed 1 \(random\)$/]); // Newest first.
      await expect(entries.locator(".text")).toHaveText([texts[2], texts[1], texts[0]]);
      await expect(entries.first().locator(".shots img")).toHaveCount(1); // Each run's image.
      await expect(entries.first().locator(".shots img")).toHaveJSProperty("naturalWidth", 32);
      const files = await entries.locator(".shots img").evaluateAll((pictures) => pictures.map((picture) => new URL(picture.src).searchParams.get("filename")));
      expect(new Set(files).size).toBe(3); // A different image for each run.
      await setWidget(page, encode, "control_after_generate", "fixed");
      await setWidget(page, encode, "seed", 3);
      await queueFromPage(page, request); // The same as the newest: not added again, its image joins the entry.
      await expect(entries).toHaveCount(3);
      await expect(entries.first().locator(".shots img")).toHaveCount(1); // The same image again (same color): once.
      await entries.nth(2).locator(".reseed").click(); // Seed 1 again: its prompts, seed and mode.
      expect(await widgetValue(page, encode, "seed")).toBe(1);
      expect(await widgetValue(page, encode, "control_after_generate")).toBe("fixed");
      await queueFromPage(page, request);
      await expect(entries.first().locator(".when")).toContainText("seed 1 (random)");
      expect(await lastRun()).toBe(texts[0]); // The same prompts as that run.
      await expect(entries).toHaveCount(4); // That run is the newest now.
      await entries.filter({ hasText: "seed 2 (random)" }).locator(".use-text").click();
      expect(await widgetValue(page, encode, "positive")).toBe(texts[1]); // Every choice made.
      await entries.last().locator(".pin").click();
      await expect(entries.last()).toHaveClass(/pinned/);
      await entries.first().locator(".forget").click();
      await expect(entries).toHaveCount(3);
      await page.keyboard.press("Escape");
      await expect(dialog).toHaveCount(0);
      await page.evaluate(([id, filler]) => { // Many unpinned runs: only the last 20 stay, a pinned one stays too.
        const node = window.app.graph.getNodeById(id);
        const pinned = node.properties.dice_forge_history.filter((item) => item.pinned);
        node.properties.dice_forge_history = [...filler, ...pinned];
      }, [encode, Array.from({ length: 25 }, (_, index) => ({ positive: `old ${index}`, negative: "", seed: 100 + index, seed_mode: "random", time: index + 1 }))]);
      await setWidget(page, encode, "positive", "a {big|small} boat");
      await queueFromPage(page, request);
      await clickMenu(page, encode, "DiceForge.PromptPreview", "Prompt history");
      await expect(dialog.locator(".top .muted")).toHaveText("21 runs, newest first");
      await expect(dialog.locator(".pin.on")).toHaveCount(1);
      await page.keyboard.press("Escape");
      const workflow = await page.evaluate(() => window.app.graph.serialize()); // Kept with the workflow.
      expect(workflow.nodes.find((node) => String(node.id) === String(encode)).properties.dice_forge_history).toHaveLength(21);
    });

    test("the images a run makes don't get the nodes' last runs: the workflow the run sends has no prompt history, Danbooru post or picked file, the graph keeps them", async ({ page }) => {
      const ids = await addNodes(page, [
        { type: "DiceForgeCLIPDualTextEncode", widgets: { positive: "a car" } },
        { type: "DiceForgeDanbooruEnhancer", pos: [500, 40] },
        { type: "DiceForgeRandomImage", pos: [40, 520] },
      ]);
      const runData = { dice_forge_history: [{ positive: "an earlier prompt", negative: "", seed: 1, seed_mode: "random", time: 1 }],
        dice_forge_danbooru: { text: "an earlier prompt, 1girl" }, dice_forge_image: { file_name: "cat.png", seed: 1, seed_mode: "random" } };
      const keys = Object.keys(runData);
      await page.evaluate(([ids, runData]) => {
        ids.forEach((id, index) => { const key = Object.keys(runData)[index]; window.app.graph.getNodeById(id).properties[key] = runData[key]; });
      }, [ids, runData]);
      let sent = null;
      await page.route("**/api/prompt", (route) => { // The run's request is answered here: nothing runs.
        if (route.request().method() !== "POST") return route.continue();
        sent = route.request().postDataJSON();
        return route.fulfill({ json: { prompt_id: "dice-forge-no-run-data", number: 0, node_errors: {} } });
      });
      await page.evaluate(() => window.app.queuePrompt(0));
      await expect.poll(() => sent).not.toBeNull();
      await page.unroute("**/api/prompt");
      const nodes = sent.extra_data.extra_pnginfo.workflow.nodes; // What the images get.
      ids.forEach((id, index) => expect(nodes.find((item) => String(item.id) === String(id)).properties).not.toHaveProperty(keys[index]));
      const graph = await page.evaluate(([ids, keys]) => ids.map((id, index) => keys[index] in window.app.graph.getNodeById(id).properties), [ids, keys]);
      expect(graph).toEqual([true, true, true]); // The graph keeps them.
    });

    test("Danbooru Tag Enhancer keeps one row about the post it took, shows the run in a window, and fills in post_ids for fixed mode, also after a reload", async ({ page, request }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeDanbooruEnhancer", widgets: { tags: "hatsune miku" } }]);
      const row = page.locator(".dfdb").first();
      await expect(row).toContainText("Run the workflow to see the Danbooru posts it takes and the tags they add here.");
      const before = (await row.boundingBox()).height;
      await queueFromPage(page, request); // An output node: it runs with nothing connected.
      await expect(row.locator(".last-run")).toHaveText("Last run: post #101 (general), +3 tags"); // Post 101: rating:g.
      expect((await row.boundingBox()).height).toBeCloseTo(before, 0); // A run doesn't make the node taller.
      await expect(row.locator("img")).toHaveCount(0); // The pictures are in the window.
      await row.locator(".last-run").click();
      const posts = page.locator(".dfdbw");
      await expect(posts.locator(".added")).toHaveText("+ 1girl, smile, twintails");
      await expect(posts.locator(".search")).toHaveText("Searched: hatsune_miku rating:g");
      await expect(posts.locator("a.thumb")).toHaveAttribute("href", /\/posts\/101$/);
      await expect(posts.locator("a.thumb img")).toHaveJSProperty("naturalWidth", 8); // The post's picture.
      await expect.poll(() => widgetValue(page, id, "post_ids")).toBe("101"); // For fixed mode.
      await posts.locator("button.keep").click();
      await expect(posts.locator("button.keep")).toHaveText("Kept (fixed)");
      await expect(posts.locator("button.keep")).toBeDisabled();
      expect(await widgetValue(page, id, "mode")).toBe("fixed");
      await queueFromPage(page, request);
      await expect(posts.locator(".search")).toHaveText("Fixed: post 101"); // The open window shows the new run.
      await page.keyboard.press("Escape");
      await expect(posts).toHaveCount(0);
      await expect(row.locator(".last-run")).toHaveText("Last run: post #101 (general), +3 tags · fixed");
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      expect(workflow.nodes.find((node) => String(node.id) === String(id)).properties.dice_forge_danbooru.post_ids).toBe("101");
      await page.evaluate(async (data) => { window.app.graph.clear(); await window.app.loadGraphData(data); }, workflow);
      await expect(page.locator(".dfdb .last-run").first()).toHaveText("Last run: post #101 (general), +3 tags · fixed"); // Kept with the workflow.
    });

    test("Danbooru Tag Enhancer's window: pictures of fixed posts, blurred past general, a link for one that won't load; e621; the node menu", async ({ page, request }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeDanbooruEnhancer", widgets: { tags: "hatsune miku", mode: "fixed", post_ids: "https://danbooru.donmai.us/posts/101, 102 103", wildcard_seed: 5 } }]);
      const extension = "DiceForge.DanbooruPreview";
      expect(await menuItems(page, id, extension)).toEqual(["🏷 Danbooru posts of the last run…"]); // Nothing to copy before a run.
      await queueFromPage(page, request);
      await expect(page.locator(".dfdb .last-run").first()).toHaveText(/^Last run: 3 posts, (\+\d+ tags?|no tags added) · fixed$/);
      expect(await menuItems(page, id, extension)).toEqual(["🏷 Danbooru posts of the last run…", "📋 Copy the added tags"]);
      await clickMenu(page, id, extension, "Danbooru posts");
      const posts = page.locator(".dfdbw");
      await expect(posts.locator(".search")).toHaveText("Fixed: posts 101, 102, 103");
      await expect(posts.locator("button.keep")).toHaveText("Keep these posts (fixed)"); // Fixed, but on the post_ids as typed.
      await expect(posts.locator("a.thumb img")).toHaveCount(2);
      await expect(posts.locator("a.thumb img").first()).not.toHaveClass(/blur/); // General.
      const explicit = posts.locator("a.thumb img").nth(1);
      await expect(explicit).toHaveClass(/blur/); // Explicit: blurred while Blur NSFW is on.
      await expect(posts.locator("a.thumb.plain")).toHaveText("↗ #103"); // Its picture didn't load: the link to the post.
      const tabs = page.context().pages().length;
      await explicit.click();
      await expect(explicit).not.toHaveClass(/blur/); // The first click only reveals...
      expect(page.context().pages()).toHaveLength(tabs); // ...and opens nothing.
      expect(await widgetValue(page, id, "post_ids")).toBe("https://danbooru.donmai.us/posts/101, 102 103"); // Fixed: your post_ids stay as typed,
      expect(await widgetValue(page, id, "wildcard_seed")).toBe(5); // and the seed.
      await posts.getByRole("button", { name: "Close" }).click();
      await expect(posts).toHaveCount(0);

      await setWidget(page, id, "mode", "random");
      await setWidget(page, id, "source", "e621");
      await setWidget(page, id, "tags", "fox, anthro");
      await queueFromPage(page, request);
      await expect(page.locator(".dfdb .last-run").first()).toHaveText("Last run: e621 post #201 (safe), +3 tags");
      await expect.poll(() => widgetValue(page, id, "post_ids")).toBe("201"); // Random: this run's post, for fixed mode.
      await page.locator(".dfdb .last-run").first().click();
      await expect(posts.locator(".added")).toHaveText("+ solo, grin, canine");
      await expect(posts.locator("a.thumb img")).not.toHaveClass(/blur/); // e621's safe isn't blurred.
      await expect(posts.locator("button.keep")).toHaveText("Keep these posts (fixed)");
      // Post numbers are a site's own: Keep puts the run's site back, and the run is kept only while site and wildcard seed are the run's.
      await page.keyboard.press("Escape");
      await setWidget(page, id, "source", "danbooru");
      await page.locator(".dfdb .last-run").first().click();
      await posts.locator("button.keep").click();
      await expect(posts.locator("button.keep")).toHaveText("Kept (fixed)");
      expect(await widgetValue(page, id, "source")).toBe("e621");
      expect(await widgetValue(page, id, "mode")).toBe("fixed");
      await page.keyboard.press("Escape");
      await setWidget(page, id, "wildcard_seed", (await widgetValue(page, id, "wildcard_seed")) + 1);
      await page.locator(".dfdb .last-run").first().click();
      await expect(posts.locator("button.keep")).toHaveText("Keep these posts (fixed)");
      await expect(posts.locator("button.keep")).toBeEnabled();
    });

    test("Danbooru Tag Enhancer: the posts a shared workflow carries link only to web addresses, never to a script", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeDanbooruEnhancer", widgets: { tags: "hatsune miku" } }]);
      // As a workflow from someone else gives it: the last run's posts in the node's properties, with a javascript: link.
      await page.evaluate((id) => {
        window.app.graph.getNodeById(id).properties.dice_forge_danbooru = { site: "danbooru", mode: "random", search: "", added: "smile",
          posts: [{ id: 7, url: "javascript:window.diceForgeRan = true", preview: "", rating: "g" }, { id: 8, url: "https://danbooru.donmai.us/posts/8", preview: "", rating: "g" }] };
      }, id);
      await page.locator(".dfdb .last-run").first().click();
      const links = page.locator(".dfdbw a.thumb.plain");
      await expect(links).toHaveText(["↗ #7", "↗ #8"]);
      await expect(links.first()).toHaveAttribute("href", ""); // Left empty: nothing to run.
      await expect(links.nth(1)).toHaveAttribute("href", "https://danbooru.donmai.us/posts/8");
      await links.first().evaluate((link) => link.addEventListener("click", (event) => event.preventDefault())); // No new tab in the test.
      await links.first().click();
      expect(await page.evaluate(() => window.diceForgeRan ?? false)).toBe(false);
    });
  });
}
