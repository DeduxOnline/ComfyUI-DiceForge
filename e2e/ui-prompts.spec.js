// End-to-end in the browser, the prompts: autocomplete, syntax highlighting, the Wildcard Browser, Wildcards to Text, the Syntax guide,
// prompt styles, the tag autocomplete, the prompt preview and history, and Danbooru Tag Enhancer, in both node designs (Nodes 2.0 and
// classic), against the real server. Each test builds its own graph.
const fs = require("fs");
const { test, expect, basePath, writeFile, openComfy, addNodes, connect, widgetValue, setWidget, menuItems, clickMenu, queueFromPage } = require("./helpers");
const { png, zip } = require("./fixtures");
const { promptField, lookUp } = require("./ui-shared");

for (const vue of [true, false]) {
  test.describe(vue ? "Nodes 2.0" : "classic nodes", () => {
    test.beforeEach(async ({ page }) => openComfy(page, { vue }));

    test("typing __ in CLIP Dual Text Encode suggests wildcards", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
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
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [100, 60], widgets: {
        positive: "masterpiece, best quality, 1girl, __color__ hair, multiple views, dynamic pose, from above, standing, looking at viewer, long hair" } }]);
      await page.evaluate(() => { window.app.canvas.ds.scale = 1.5; window.app.canvas.setDirty(true, true); });
      await page.waitForTimeout(500);
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
      let requests = 0;
      await page.route("**/diceforge/wildcards", async (route) => {
        const delay = [900, 300, 50][Math.min(requests++, 2)]; // Later requests answer sooner: answers come back out of order.
        await new Promise((resolve) => setTimeout(resolve, delay));
        await route.continue();
      });
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      const positive = await promptField(page, id, "positive");
      await positive.click();
      await page.keyboard.type("__hair/st");
      await page.waitForTimeout(1500); // Every answer is in.
      await expect(page.locator(".dfwc-pop div").first()).toContainText("__hair/style__");
      await page.keyboard.press("Enter");
      await expect.poll(() => widgetValue(page, id, "positive")).toBe("__hair/style__");
      expect(requests).toBe(1); // One shared request, not one per keystroke.
    });

    test("the prompt fields highlight the syntax, with missing wildcards in red", async ({ page }) => {
      const prompt = "${g={male|female}}a __color__ {2$$3::!hat|__nope__|bow} \\{x\\} (smile:1.2) ${g} // note\n/* block */ embedding:easy";
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", widgets: { positive: prompt } }]);
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
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60], widgets: { positive: "1girl" } }]);
      expect(await menuItems(page, id, "DiceForge.Wildcards")).toEqual(["📖 Syntax guide", "🎲 Wildcard Browser"]);
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
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      await page.evaluate(() => localStorage.removeItem("diceforge.wildcards.open"));
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const hair = page.locator('.dfwc .folder[data-path="hair"]');
      const style = hair.locator(".row", { hasText: "style" });
      await expect(hair).not.toHaveClass(/open/); // Folders start closed.
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
      await expect(page.locator('.dfwc .folder[data-path="characters/alice"] .row', { hasText: "outfit" })).toBeVisible();
      await page.locator(".dfwc button.close-all").click();
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser moves files: Move picks a folder, a file dropped on a folder moves there", async ({ page }) => {
      const top = `wmove_${vue ? "vue" : "classic"}`, wildcards = (...parts) => basePath("models", "wildcards", ...parts);
      writeFile(`models/wildcards/${top}/from/x.txt`, "one\ntwo\n");
      writeFile(`models/wildcards/${top}/to/y.txt`, "y\n");
      try {
        const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
        await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
        await page.locator(".dfwc button.open-all").click();
        await page.locator(`.dfwc .row[data-name="${top}/from/x"] .name`).click();
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

    test("Wildcard Browser favorites: ☆ stars a file, ★ Favorites shows only them, the autocomplete puts them first", async ({ page }) => {
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
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
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60], widgets: { positive: "1girl" } }]);
      page.on("dialog", (confirmation) => confirmation.accept());
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      if (await dialog.locator("button.mode").textContent() === "📄 Lines") await dialog.locator("button.mode").click(); // Start in lines.
      const folder = dialog.locator(`.folder[data-path="${pack}"] > .row`);
      await folder.locator("button.convert", { hasText: "→ yaml" }).click();
      await expect(dialog.locator(".status")).toContainText("Converted 2 wildcards into");
      expect(fs.existsSync(file(`${pack}.yaml`))).toBe(true);
      expect(fs.existsSync(file(pack, "sitting.txt"))).toBe(false);
      await expect(folder.locator("button.convert")).toHaveText("→ txt"); // The same names, now from the yaml file.
      await dialog.locator("button.mode").click(); // Cards: a picture for a card.
      await folder.locator(".name").click();
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
      await folder.locator("button.convert", { hasText: "→ txt" }).click();
      await expect(dialog.locator(".status")).toContainText(`${pack}.yaml into 2 txt files`);
      expect(fs.readFileSync(file(pack, "standing.txt"), "utf8")).toBe("standing\nstanding, arms crossed\n");
      expect(fs.existsSync(file(`${pack}.yaml`))).toBe(false);
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser's editor has the autocomplete: wildcards and LoRAs while typing, Escape closes only the list", async ({ page }) => {
      const file = `complete_${vue ? "vue" : "classic"}`; // A file of its own: the tests share the server's files.
      writeFile(`models/wildcards/${file}.txt`, "one\n");
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      if (await dialog.locator("button.mode").textContent() === "📄 Lines") await dialog.locator("button.mode").click(); // Lines: the editor.
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
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60], widgets: { positive: "1girl" } }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      if (await dialog.locator("button.mode").textContent() === "📄 Lines") await dialog.locator("button.mode").click(); // Lines: the editor.
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
      const again = page.waitForEvent("filechooser"); // The same zip again: what is there is kept.
      await dialog.locator("button.import").click();
      await (await again).setFiles({ name: `${pack}.zip`, mimeType: "application/zip", buffer: zip({ [`${pack}.yaml`]: "changed: [x]\n" }) });
      await expect(dialog.locator(".status")).toHaveText(`Imported 0 files from ${pack}.zip; 1 already there, kept as they were.`);
      await page.keyboard.press("Escape");
    });

    test("Wildcard Browser creates, renames and deletes files", async ({ page }) => {
      const tag = vue ? "vue" : "classic", wildcards = (...parts) => basePath("models", "wildcards", ...parts);
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const answers = [`crud_${tag}/new`, `crud_${tag}/new`, `crud_${tag}_done/renamed`]; // The prompts in order: new file, the same name again, rename.
      page.on("dialog", (dialog) => (dialog.type() === "confirm" ? dialog.accept() : dialog.accept(answers.shift())));
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
      expect(fs.existsSync(wildcards(`crud_${tag}`))).toBe(false);
      await page.locator(".dfwc button.delete").click();
      await expect(status).toContainText(`Deleted crud_${tag}_done/renamed.txt`);
      expect(fs.existsSync(wildcards(`crud_${tag}_done`))).toBe(false);
      await expect(page.locator(".dfwc .row", { hasText: `crud_${tag}` })).toHaveCount(0);
      await expect(page.locator(".dfwc button.delete")).toBeDisabled();
      await page.locator(".dfwc button.open-all").click(); // The yaml wildcards are in closed folders.
      await page.locator(".dfwc .row", { hasText: "outfit" }).filter({ hasText: "yaml" }).first().locator(".name").click(); // yaml: read-only.
      await expect(page.locator(".dfwc button.rename")).toBeDisabled();
      await expect(page.locator(".dfwc button.delete")).toBeDisabled();
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
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60], widgets: { positive: "1girl" } }]);
      await clickMenu(page, id, "DiceForge.Wildcards", "Wildcard Browser");
      const dialog = page.locator(".dfwc");
      if (await dialog.locator("button.mode").textContent() === "📄 Lines") await dialog.locator("button.mode").click(); // Start in lines.
      await expect(dialog.locator("button.mode")).toHaveText("🃏 Cards");
      await dialog.locator("button.mode").click();
      await dialog.locator(".folder > .row .name", { hasText: pack }).click(); // The folder's cards.
      await expect(dialog.locator(".cards-head b")).toHaveText(`📁 ${pack}`);
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
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60], widgets: { positive: "1girl" } }]);
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
    });

    test("Prompt styles: the family's quality tags in and out with a click, Auto from the connected model, your own saved and deleted", async ({ page, request }) => {
      await lookUp(request, "checkpoints", "illustrious_base.safetensors");
      const [checkpoint, encode] = await addNodes(page, [
        { type: "CheckpointLoaderSimple", widgets: { ckpt_name: "illustrious_base.safetensors" } },
        { type: "CLIPTextEncodePositiveNegative", pos: [460, 40], widgets: { positive: "1girl, smile", negative: "" } },
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
      page.on("dialog", (dialog) => (dialog.type() === "prompt" ? dialog.accept(`E2E film ${vue}`) : dialog.accept()));
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
      const [id] = await addNodes(page, [{ type: "CLIPTextEncodePositiveNegative", pos: [300, 60] }]);
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
      } finally {
        fs.rmSync(basePath("user", "DiceForge", "tags"), { recursive: true, force: true }); // No tag suggestions in the other tests.
        fs.rmSync(basePath("user", "DiceForge", "tag_favorites.json"), { force: true });
      }
    });

    test("a workflow saved when model was the last output keeps its connections: they follow their outputs", async ({ page, request }) => {
      const [encode, preview] = await addNodes(page, [
        { type: "CLIPTextEncodePositiveNegative", widgets: { positive: "an old {saved|saved} workflow" } }, { type: "PreviewAny", pos: [600, 40] }]);
      await connect(page, encode, 3, preview, 0);
      const saved = await page.evaluate((id) => { // As saved before: positive, negative, positive_text, negative_text, model; the link from slot 2.
        const data = window.app.graph.serialize();
        const node = data.nodes.find((item) => String(item.id) === String(id));
        const order = ["positive", "negative", "positive_text", "negative_text", "model"];
        node.outputs = order.map((name) => node.outputs.find((output) => output.name === name));
        for (const link of data.links) if (String(link[1]) === String(id)) link[2] = order.indexOf("positive_text");
        return data;
      }, encode);
      await page.evaluate(async (data) => { window.app.graph.clear(); await window.app.loadGraphData(data); }, saved);
      expect(await page.evaluate((id) => window.app.graph.getNodeById(id).outputs.map((output) => output.name), encode))
        .toEqual(["model", "positive", "negative", "positive_text", "negative_text"]);
      await queueFromPage(page, request);
      const history = Object.values(await (await request.get("/history?max_items=1")).json())[0];
      expect(history.outputs[String(preview)].text[0]).toBe("an old saved workflow"); // Still from positive_text, now slot 3.
    });

    test("a workflow queued from the page fills in the prompt", async ({ page, request }) => {
      const [encode, preview] = await addNodes(page, [
        { type: "CLIPTextEncodePositiveNegative", widgets: { positive: "a __color__ car, {2$$__characters/*/outfit__}", seed: 3 } },
        { type: "PreviewAny", pos: [500, 40] },
      ]);
      await connect(page, encode, 3, preview, 0);
      await queueFromPage(page, request);
      const history = Object.values(await (await request.get("/history?max_items=1")).json())[0];
      const text = history.outputs[String(preview)].text[0];
      expect(text).toMatch(/^a (red|blue|green|white) car, [a-z ]+, [a-z ]+$/);
      // The node shows the prompts as encoded, with the seed they came from.
      const shown = page.locator(".dfpp").first();
      await expect(shown.locator(".box").first()).toHaveText(`positive${text}`);
      if (vue) { // The negative shows with the advanced inputs, where its field is.
        await expect(shown.locator(".box")).toHaveCount(1);
        await page.evaluate((id) => { const node = window.app.graph.getNodeById(id); node.showAdvanced = true; node.setDirtyCanvas(true, true); }, encode);
      }
      await expect(shown.locator(".box").nth(1)).toContainText("(empty)");
      if (vue) { // And hides with them again.
        await page.evaluate((id) => { const node = window.app.graph.getNodeById(id); node.showAdvanced = false; node.setDirtyCanvas(true, true); }, encode);
        await expect(shown.locator(".box")).toHaveCount(1);
      }
      await expect(shown.locator(".head")).toContainText("seed 3 (random)");
      await expect(shown).not.toHaveClass(/stale/);
      await setWidget(page, encode, "positive", "a __color__ bike"); // Changed since the run: dimmed until the next one.
      await expect(shown).toHaveClass(/stale/);
      await expect(shown.locator(".changed")).toHaveText("prompt changed since");
      // Kept with the workflow: a reload of it shows them again.
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      expect(workflow.nodes.find((node) => String(node.id) === String(encode)).properties.dice_forge_prompts.positive).toBe(text);
      await page.evaluate(async (data) => { window.app.graph.clear(); await window.app.loadGraphData(data); }, workflow);
      await expect(page.locator(".dfpp").first().locator(".box").first()).toHaveText(`positive${text}`);
    });

    test("the prompt history keeps the last runs with their images: put back a seed, use a text, pin, remove", async ({ page, request }) => {
      const [encode, preview, image, show] = await addNodes(page, [
        { type: "CLIPTextEncodePositiveNegative", widgets: { positive: "a {red|blue|green|white|black|pink} car", seed: 1, control_after_generate: "increment" } },
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
      const panel = page.locator(".dfpp").first();
      const lastRun = async () => (await panel.locator(".box").first().textContent()).replace(/^positive/, "");
      const texts = (await page.evaluate((id) => window.app.graph.getNodeById(id).properties.dice_forge_history.map((item) => item.positive), encode)).reverse();
      await expect(panel.locator(".history-link")).toHaveCount(0); // Not on the node: in its right-click menu.
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
      await expect(panel.locator(".head")).toContainText("seed 1 (random)");
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

    test("Danbooru Tag Enhancer shows the post it took and fills in post_ids for fixed mode, also after a reload", async ({ page, request }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeDanbooruEnhancer", widgets: { tags: "hatsune miku" } }]);
      const panel = page.locator(".dfdb").first();
      await expect(panel).toContainText("Run the workflow to see the Danbooru posts it takes and the tags they add here.");
      await queueFromPage(page, request); // An output node: it runs with nothing connected.
      await expect(panel.locator(".added")).toHaveText("+ 1girl, smile, twintails"); // Post 101: rating:g.
      await expect(panel.locator(".head")).toHaveText("Last run · post #101 (general)");
      await expect(panel.locator(".search")).toHaveText("Searched: hatsune_miku rating:g");
      await expect(panel.locator("a.thumb")).toHaveAttribute("href", /\/posts\/101$/);
      await expect(panel.locator("a.thumb img")).toHaveJSProperty("naturalWidth", 8); // The post's picture.
      await expect.poll(() => widgetValue(page, id, "post_ids")).toBe("101"); // For fixed mode.
      await setWidget(page, id, "mode", "fixed");
      await queueFromPage(page, request);
      await expect(panel.locator(".head")).toHaveText("Last run · post #101 (general) · fixed");
      await expect(panel.locator(".search")).toHaveText("Fixed: post 101");
      const workflow = await page.evaluate(() => window.app.graph.serialize());
      expect(workflow.nodes.find((node) => String(node.id) === String(id)).properties.dice_forge_danbooru.post_ids).toBe("101");
      await page.evaluate(async (data) => { window.app.graph.clear(); await window.app.loadGraphData(data); }, workflow);
      await expect(page.locator(".dfdb").first().locator(".added")).toHaveText("+ 1girl, smile, twintails"); // Kept with the workflow.
    });

    test("Danbooru Tag Enhancer previews: pictures of fixed posts, blurred past general, a link for one that won't load; e621; an older result", async ({ page, request }) => {
      const [id] = await addNodes(page, [{ type: "DiceForgeDanbooruEnhancer", widgets: { tags: "hatsune miku", mode: "fixed", post_ids: "https://danbooru.donmai.us/posts/101, 102 103", wildcard_seed: 5 } }]);
      const panel = page.locator(".dfdb").first();
      await queueFromPage(page, request);
      await expect(panel.locator(".head")).toHaveText("Last run · 3 posts · fixed");
      await expect(panel.locator(".search")).toHaveText("Fixed: posts 101, 102, 103");
      await expect(panel.locator("a.thumb img")).toHaveCount(2);
      await expect(panel.locator("a.thumb img").first()).not.toHaveClass(/blur/); // General.
      const explicit = panel.locator("a.thumb img").nth(1);
      await expect(explicit).toHaveClass(/blur/); // Explicit: blurred while Blur NSFW is on.
      await expect(panel.locator("a.thumb.plain")).toHaveText("↗ #103"); // Its picture didn't load: the link to the post.
      const tabs = page.context().pages().length;
      await explicit.click();
      await expect(explicit).not.toHaveClass(/blur/); // The first click only reveals...
      expect(page.context().pages()).toHaveLength(tabs); // ...and opens nothing.
      expect(await widgetValue(page, id, "post_ids")).toBe("https://danbooru.donmai.us/posts/101, 102 103"); // Fixed: your post_ids stay as typed,
      expect(await widgetValue(page, id, "wildcard_seed")).toBe(5); // and the seed.

      await setWidget(page, id, "mode", "random");
      await setWidget(page, id, "source", "e621");
      await setWidget(page, id, "tags", "fox, anthro");
      await queueFromPage(page, request);
      await expect(panel.locator(".head")).toHaveText("Last run · e621 post #201 (safe)");
      await expect(panel.locator(".added")).toHaveText("+ solo, grin, canine");
      await expect(panel.locator("a.thumb img")).not.toHaveClass(/blur/); // e621's safe isn't blurred.
      await expect.poll(() => widgetValue(page, id, "post_ids")).toBe("201"); // Random: this run's post, for fixed mode.

      await page.evaluate((nodeId) => { // A result saved by an older version (one post, no posts list).
        window.app.graph.getNodeById(nodeId).properties.dice_forge_danbooru = { text: "x, smile", added: "smile", url: "https://danbooru.donmai.us/posts/7", id: 7, search: "x rating:s", rating: "s" };
      }, id);
      await expect(panel.locator(".head")).toHaveText("Last run · post #7 (sensitive)");
      await expect(panel.locator("a.thumb.plain")).toHaveAttribute("href", /\/posts\/7$/);
      await expect(panel.locator(".added")).toHaveText("+ smile");
    });
  });
}
