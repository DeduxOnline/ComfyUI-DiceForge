// End-to-end robustness on the real ComfyUI server: what DiceForge does under bad conditions that only a running server shows. Damaged files put
// into the server's folders while it runs, junk and path-escaping HTTP requests through ComfyUI's own middleware, node errors (the server must keep
// working after each), prompts ComfyUI refuses, many prompts queued at once, every seed mode through the queue, and text in any script.
const fs = require("fs");
const path = require("path");
const { test, expect, runPrompt, shown, basePath, writeFile } = require("./helpers");
const { BASE } = require("./settings");

const MODES = ["random", "deck", "shuffle", "balanced", "combinations", "mutate"];
const clip = (positive, negative = "", { seed = 0, mode = "random" } = {}) => ({
  1: { class_type: "CLIPTextEncodePositiveNegative", inputs: { positive, negative, seed, seed_mode: mode, trim: true } },
  2: { class_type: "PreviewAny", inputs: { source: ["1", 2] } },
  3: { class_type: "PreviewAny", inputs: { source: ["1", 3] } },
});
const sdxl = (inputs) => ({
  1: { class_type: "SDXLResolutionListLatent", inputs: { resolution: "Standard", "resolution.size": "1024 x 1024", seed: 0, rescale: "by percentage", "rescale.percent": 100, multiple: 8, batch: 1, seed_mode: "random", ...inputs } },
  2: { class_type: "PreviewAny", inputs: { source: ["1", 1] } },
  3: { class_type: "PreviewAny", inputs: { source: ["1", 2] } },
});
const randomInt = (inputs) => ({
  1: { class_type: "DiceForgeRandomInt", inputs: { min: 1, max: 5, step: 1, seed: 0, seed_mode: "random", ...inputs } },
  2: { class_type: "PreviewAny", inputs: { source: ["1", 0] } },
});
const DICEFORGE = (...parts) => basePath("user", "DiceForge", ...parts);
// The server still runs prompts normally (after an error, a refused prompt or a damaged file).
async function stillWorks(request) {
  const seed = Math.floor(Math.random() * 1e9);
  const result = await runPrompt(request, clip("alive {a|b}", "", { seed }));
  expect(result.status).toBe("success");
  expect(["alive a", "alive b"]).toContain(shown(result, "2"));
}
const remove = (...files) => { for (const file of files) fs.rmSync(file, { recursive: true, force: true }); };

test.describe("@api robustness on the real server", () => {
  test("junk requests to every DiceForge route are answered with 4xx, never a server error", async ({ request }) => {
    const bodies = ["not json", "", "[]", "5", "null", '"text"', '{"loras": 5}', '{"loras": [1, null, {"a": 1}]}', '{"items": [1, null, {"kind": 5, "file": []}]}',
      '{"kind": "loras", "file": "x", "user": [1]}', '{"name": 5}', '{"name": "ok", "stack": 5}', '{"name": "ok", "stack": {"rows": "x"}}', '{"name": ["a"]}',
      '{"name": "' + "x".repeat(5000) + '", "text": "y"}', '{"name": "' + "x".repeat(5000) + '", "stack": {"rows": []}}', "{".repeat(10000)];
    const posts = ["/diceforge/wildcards/file", "/diceforge/wildcards/rename", "/diceforge/models/rename", "/diceforge/civitai/download", "/diceforge/civitai/key", "/diceforge/lora-presets", "/diceforge/lora-triggers", "/diceforge/model-bases", "/diceforge/model-info"];
    for (const route of posts) {
      for (const body of bodies) {
        const response = await request.post(route, { data: body, headers: { "Content-Type": "application/json" } });
        expect(response.status(), `${route} ${body.slice(0, 40)}`).toBeLessThan(500);
        if (response.status() >= 400) expect((await response.text()).length, `${route}: a message`).toBeGreaterThan(0);
      }
    }
    const gets = ["/diceforge/model-info?kind=loras&file=nope", "/diceforge/model-info?kind=x&file=y", "/diceforge/model-info", "/diceforge/model-browser?kind=nope",
      "/diceforge/model-browser", "/diceforge/model-preview?kind=loras&file=nope.safetensors", "/diceforge/model-preview", "/diceforge/wildcards/file",
      "/diceforge/wildcards/file?name=", "/diceforge/wildcards/file?name=%00", "/diceforge/lora-presets/file?name=", "/diceforge/lora-presets/file?name=%00x"];
    for (const route of gets) expect((await request.get(route)).status(), route).toBeLessThan(500);
    expect((await request.delete("/diceforge/lora-presets?name=")).status()).toBeLessThan(500);
    for (const route of ["/diceforge/wildcards/file", "/diceforge/wildcards/file?name=", "/diceforge/wildcards/file?name=%00", "/diceforge/wildcards/file?name=nope",
      "/diceforge/models/file", "/diceforge/models/file?kind=loras&file=", "/diceforge/models/file?kind=loras&file=%00", "/diceforge/models/file?kind=vae&file=x",
      "/diceforge/civitai/downloads", "/diceforge/civitai/downloads?id=nope"])
      expect((await request.delete(route)).status(), route).toBeLessThan(500);
    await stillWorks(request);
  });

  test("no request reaches a file outside DiceForge's folders", async ({ request }) => {
    const outside = path.join(path.dirname(BASE), "diceforge-e2e-secret.json");
    fs.writeFileSync(outside, JSON.stringify({ stack: { rows: [{ lora: "secret" }] }, secret: true }));
    const escapes = ["../../diceforge-e2e-secret", "..%2F..%2Fdiceforge-e2e-secret", "../../../diceforge-e2e-secret", "/etc/passwd", "a/../../../x", "..\\..\\x", "C:\\Windows\\win",
      `${path.dirname(BASE)}/diceforge-e2e-secret`];
    try {
      for (const name of escapes) {
        const encoded = encodeURIComponent(name);
        for (const response of [
          await request.get(`/diceforge/lora-presets/file?name=${encoded}`),
          await request.get(`/diceforge/wildcards/file?name=${encoded}`),
          await request.get(`/diceforge/model-preview?kind=loras&file=${encoded}`),
          await request.get(`/diceforge/model-info?kind=loras&file=${encoded}`),
        ]) {
          expect(response.status(), name).toBeGreaterThanOrEqual(400);
          expect(await response.text(), name).not.toContain("secret\": true");
        }
        for (const response of [
          await request.post("/diceforge/wildcards/file", { data: { name, text: "escaped" } }),
          await request.post("/diceforge/lora-presets", { data: { name, stack: { rows: [] }, overwrite: true } }),
          await request.post("/diceforge/model-info", { data: { kind: "loras", file: name, user: { notes: "escaped" } } }),
          await request.delete(`/diceforge/lora-presets?name=${encoded}`),
          await request.delete(`/diceforge/wildcards/file?name=${encoded}`),
          await request.post("/diceforge/wildcards/rename", { data: { name, to: "escaped" } }),
          await request.post("/diceforge/wildcards/rename", { data: { name: "weighted", to: name } }),
          await request.delete(`/diceforge/models/file?kind=loras&file=${encoded}`),
          await request.post("/diceforge/models/rename", { data: { kind: "loras", file: name, to: "escaped" } }),
        ]) expect(response.status(), name).toBeGreaterThanOrEqual(400);
        // A new name or a download folder: refused, or (a name like "..%2Fx" is a real file name) a file inside models/loras, put back afterwards.
        const loras = basePath("models", "loras"), isInside = (file) => path.resolve(loras, file).startsWith(loras + path.sep);
        writeFile("models/loras/e2e_escape.safetensors", "x");
        const renamed = await request.post("/diceforge/models/rename", { data: { kind: "loras", file: "e2e_escape.safetensors", to: name } });
        if (renamed.ok()) {
          const { to } = await renamed.json();
          expect(isInside(to), `${name} -> ${to}`).toBe(true);
          expect((await request.delete(`/diceforge/models/file?kind=loras&file=${encodeURIComponent(to)}`)).ok()).toBe(true);
        } else {
          expect(renamed.status(), name).toBeGreaterThanOrEqual(400);
          expect((await request.delete("/diceforge/models/file?kind=loras&file=e2e_escape.safetensors")).ok()).toBe(true);
        }
        const download = await request.post("/diceforge/civitai/download", { data: { kind: "loras", version_id: 501, folder: name } });
        if (download.ok()) {
          const job = await download.json();
          expect(isInside(job.file), `${name} -> ${job.file}`).toBe(true);
          await expect.poll(async () => (await (await request.get("/diceforge/civitai/downloads")).json()).jobs.find((entry) => entry.id === job.id).status).toBe("done");
          expect((await request.delete(`/diceforge/models/file?kind=loras&file=${encodeURIComponent(job.file)}`)).ok()).toBe(true);
        } else expect(download.status(), name).toBeGreaterThanOrEqual(400);
      }
      expect(fs.readdirSync(basePath("models", "loras")).sort()).toEqual(["detail.preview.png", "detail.safetensors", "style"]); // All put back.
      expect(JSON.parse(fs.readFileSync(outside, "utf8")).secret).toBe(true); // Not overwritten or deleted.
      const strays = fs.readdirSync(path.dirname(BASE)).filter((name) => /escaped|^x\.(txt|json)$/.test(name));
      expect(strays).toEqual([]);
    } finally {
      remove(outside);
    }
  });

  test("a node error stops only that prompt, with a clear message, and the server keeps working", async ({ request }) => {
    const failures = [
      [clip("${never_set}"), "Variable ${never_set} is used but never set"],
      [clip("__nope_e2e__"), "Wildcard __nope_e2e__ not found"],
      [clip("{" + "{".repeat(80) + "a" + "}".repeat(81)), "nested too deep"],
      [clip("__outfit/${who}__"), "uses ${who}, which is not set"],
      [{ 1: { class_type: "DiceForgeRandomSampler", inputs: { samplers: "euler, not_a_sampler", schedulers: "normal", seed: 0, seed_mode: "random" } },
        2: { class_type: "PreviewAny", inputs: { source: ["1", 2] } } }, "unknown sampler not_a_sampler"],
      [{ 1: { class_type: "DiceForgeRandomImage", inputs: { folder: "(all)", seed: 0, seed_mode: "random", path: basePath("nowhere") } },
        2: { class_type: "PreviewAny", inputs: { source: ["1", 2] } } }, "Random Image"],
      [{ 1: { class_type: "SDXLResolutionListLatent", inputs: { resolution: "Standard", "resolution.size": "1024 x 1024", seed: 0, rescale: "by percentage", "rescale.percent": 100, multiple: 8, batch: 1, seed_mode: "random" } },
        2: { class_type: "DiceForgeLoraStack", inputs: { model: ["9", 0], loras: "{oops", seed: 0, seed_mode: "random" } },
        9: { class_type: "CheckpointLoaderSimple", inputs: { ckpt_name: "illustrious_base.safetensors" } } }, null], // The stand-in checkpoint fails first: still an error, not a crash.
    ];
    for (const [prompt, message] of failures) {
      const result = await runPrompt(request, prompt);
      if (result.rejected) {
        expect(JSON.stringify(result.rejected)).not.toContain("Traceback");
      } else {
        expect(result.status, JSON.stringify(prompt).slice(0, 80)).toBe("error");
        if (message) expect(result.error).toContain(message);
      }
      await stillWorks(request);
    }
  });

  test("prompts with invalid inputs are refused by ComfyUI before they run, and nothing breaks", async ({ request }) => {
    // An unknown option of a nested list (rescale "sideways") is dropped by ComfyUI itself before the node runs: the node then gets no rescale,
    // which is 100%. Documented here so a ComfyUI change in this shows up.
    const sideways = await runPrompt(request, sdxl({ rescale: "sideways", "rescale.percent": 150 }));
    expect(sideways.status).toBe("success");
    expect([shown(sideways, "2"), shown(sideways, "3")]).toEqual(["1024", "1024"]);
    const refused = [
      clip("x", "", { mode: "nonsense" }),
      sdxl({ "resolution.size": "1 x 1" }),
      sdxl({ multiple: 7 }),
      sdxl({ batch: 0 }),
      randomInt({ seed: -1 }),
      { 1: { class_type: "DiceForgeRandomFloat", inputs: { min: 0, max: 1, step: 0, seed: 0, seed_mode: "random", parts: 1 } }, 2: { class_type: "PreviewAny", inputs: { source: ["1", 0] } } },
    ];
    for (const prompt of refused) {
      const result = await runPrompt(request, prompt);
      expect(result.rejected, JSON.stringify(prompt["1"].inputs).slice(0, 120)).toBeTruthy();
    }
    await stillWorks(request);
  });

  test("a damaged seed memory file is set aside and the remembering modes keep working", async ({ request }) => {
    const memory = DICEFORGE("seed_memory.sqlite");
    expect((await runPrompt(request, randomInt({ seed_mode: "shuffle" }))).status).toBe("success"); // The file exists and is open.
    const broken = () => fs.readdirSync(DICEFORGE()).filter((name) => name.startsWith("seed_memory.sqlite.broken-"));
    const before = broken().length;
    fs.writeFileSync(memory, "not a database ".repeat(500)); // Overwritten in place while the server has it open.
    for (const mode of ["shuffle", "balanced"]) expect((await runPrompt(request, randomInt({ seed_mode: mode }))).status, mode).toBe("success");
    expect((await runPrompt(request, clip("{a|b|c}", "", { mode: "mutate" }))).status).toBe("success");
    fs.rmSync(memory);
    fs.writeFileSync(memory, Buffer.alloc(8192, 0x5a)); // Replaced by another file: a new file at the same place.
    const values = [];
    for (let run = 0; run < 5; run++) {
      const result = await runPrompt(request, randomInt({ seed_mode: "shuffle", min: 10, max: 14 }));
      expect(result.status).toBe("success");
      values.push(shown(result, "2"));
    }
    expect(values.sort()).toEqual(["10", "11", "12", "13", "14"]); // A whole shuffle round: the new memory works.
    expect(broken().length).toBeGreaterThan(before);
    expect(fs.readFileSync(memory).subarray(0, 15).toString()).toBe("SQLite format 3"); // A real database again.
  });

  test("damaged and unusual wildcard files: the rest keeps working, the browser lists them, errors name the file", async ({ request }) => {
    const folder = basePath("models", "wildcards", "e2e_damaged");
    fs.mkdirSync(folder, { recursive: true });
    try {
      fs.writeFileSync(path.join(folder, "bom.txt"), "\ufeffalpha\r\nbeta\r\n");
      fs.writeFileSync(path.join(folder, "cp1251.txt"), Buffer.from([0xea, 0xf0, 0xe0, 0xf1, 0xed, 0xfb, 0xe9, 0x0a])); // "красный" in Windows-1251.
      fs.writeFileSync(path.join(folder, "broken.yaml"), "e2e_broken: [unclosed\n  - : :\n");
      fs.writeFileSync(path.join(folder, "words.yaml"), "answers: [yes, no, 12:30, 0123]\n");
      fs.writeFileSync(path.join(folder, "empty.txt"), "# only a comment\n\n");
      writeFile("models/wildcards/e2e_damaged/цвет.txt", "красный\nсиний\n");
      const list = await (await request.get("/diceforge/wildcards")).json();
      const listed = Object.fromEntries(list.files.map((file) => [file.name, file]));
      expect(listed["e2e_damaged/cp1251"].error).toContain("not UTF-8");
      expect(listed["e2e_damaged/bom"].preview).toEqual(["alpha", "beta"]);
      expect(listed.color.lines).toBe(4); // The others are listed as usual.
      expect((await request.get("/diceforge/wildcards/file?name=e2e_damaged/cp1251")).status()).toBe(400);
      expect((await request.get(`/diceforge/wildcards/file?name=${encodeURIComponent("e2e_damaged/цвет")}`)).status()).toBe(200);
      const outputs = new Set();
      for (let seed = 0; seed < 2; seed++) outputs.add(shown(await runPrompt(request, clip("__e2e_damaged/bom__", "", { seed, mode: "deck" })), "2"));
      expect([...outputs].sort()).toEqual(["alpha", "beta"]); // No BOM in the first line.
      const words = new Set();
      for (let seed = 0; seed < 4; seed++) words.add(shown(await runPrompt(request, clip("__e2e_damaged/answers__", "", { seed, mode: "deck" })), "2"));
      expect([...words].sort()).toEqual(["0123", "12:30", "no", "yes"]); // As written, not True/False/750/83.
      const russian = new Set();
      for (let seed = 0; seed < 2; seed++) russian.add(shown(await runPrompt(request, clip("__e2e_damaged/цвет__ платье", "", { seed, mode: "deck" })), "2"));
      expect([...russian].sort()).toEqual(["красный платье", "синий платье"]);
      let result = await runPrompt(request, clip("__e2e_damaged/cp1251__"));
      expect(result.error).toMatch(/cp1251\.txt is not UTF-8/);
      result = await runPrompt(request, clip("__e2e_damaged/empty__"));
      expect(result.error).toContain("is empty");
      result = await runPrompt(request, clip("__e2e_broken__"));
      expect(result.error).toContain("not found"); // The broken yaml is skipped, not half read.
      await stillWorks(request);
    } finally {
      remove(folder);
    }
  });

  test("damaged model info and preset files don't break the browsers, the stack or the preset list", async ({ request }) => {
    const info = DICEFORGE("model_info", "loras", "detail.safetensors.json");
    const presets = DICEFORGE("lora_presets");
    fs.mkdirSync(path.dirname(info), { recursive: true });
    fs.mkdirSync(presets, { recursive: true });
    const saved = fs.existsSync(info) ? fs.readFileSync(info) : null;
    try {
      for (const damage of ["{oops", "[]", '"text"', JSON.stringify({ user: "x", civitai: [1] }), JSON.stringify({ user: { trigger_words: ["a"] }, civitai: { trigger_words: "abc", images: [null, 5] } })]) {
        fs.writeFileSync(info, damage);
        const browser = await request.get("/diceforge/model-browser?kind=loras");
        expect(browser.status(), damage).toBe(200);
        expect((await browser.json()).files.map((file) => file.file)).toContain("detail.safetensors");
        const triggers = await request.post("/diceforge/lora-triggers", { data: { loras: ["detail.safetensors"] } });
        expect(triggers.status(), damage).toBe(200);
        expect((await request.post("/diceforge/model-bases", { data: { items: [{ kind: "loras", file: "detail.safetensors" }] } })).status()).toBe(200);
        expect((await request.get("/diceforge/model-info?kind=loras&file=detail.safetensors")).status(), damage).toBe(200); // Looked up again, written fresh.
      }
      fs.writeFileSync(path.join(presets, "e2e broken.json"), "{oops");
      fs.writeFileSync(path.join(presets, "e2e list.json"), "[1, 2]");
      fs.writeFileSync(path.join(presets, "e2e good.json"), JSON.stringify({ stack: { rows: [{ lora: "detail.safetensors" }, { nope: 1 }, { lora: 5 }] } }));
      const names = (await (await request.get("/diceforge/lora-presets")).json()).presets.map((preset) => preset.name);
      expect(names).toContain("e2e good");
      expect(names).not.toContain("e2e broken");
      expect((await request.get("/diceforge/lora-presets/file?name=e2e%20broken")).status()).toBe(400);
      expect((await request.get("/diceforge/lora-presets/file?name=e2e%20list")).status()).toBe(400);
      const good = await (await request.get("/diceforge/lora-presets/file?name=e2e%20good")).json();
      expect(good.stack.rows).toEqual([{ lora: "detail.safetensors" }]); // Junk rows left out.
    } finally {
      remove(path.join(presets, "e2e broken.json"), path.join(presets, "e2e list.json"), path.join(presets, "e2e good.json"));
      if (saved) fs.writeFileSync(info, saved);
    }
  });

  test("a Dice Grid with a damaged manifest or a deleted cell keeps collecting", async ({ request }) => {
    const grid = (label) => ({ 1: { class_type: "EmptyImage", inputs: { width: 32, height: 32, batch_size: 1, color: 0x22aa22 } },
      2: { class_type: "DiceForgeGrid", inputs: { image: ["1", 0], label, count: 0, columns: 0, cell_width: 64, save: false, filename_prefix: "e2e/damaged_grid", name: "e2e_damaged", new_grid: false, legend: "", legend_position: "top", numbered: false } },
      3: { class_type: "PreviewAny", inputs: { source: ["2", 1] } } });
    const folder = DICEFORGE("grids", "e2e_damaged-2");
    remove(folder);
    expect(shown(await runPrompt(request, grid("a")), "3")).toBe("1");
    expect(shown(await runPrompt(request, grid("b")), "3")).toBe("2");
    fs.rmSync(path.join(folder, "00000.png")); // A cell deleted by hand.
    let result = await runPrompt(request, grid("c"));
    expect(result.status).toBe("success");
    expect(shown(result, "3")).toBe("2"); // b and c: the missing cell is left out.
    for (const damage of ["{oops", "[]", '{"cells": "x"}', '{"cells": [{"file": "../../../../evil.png", "label": "x", "row": ""}]}']) {
      fs.writeFileSync(path.join(folder, "manifest.json"), damage);
      result = await runPrompt(request, grid(`d ${damage.length}`));
      expect(result.status, damage).toBe("success");
      expect(Number(shown(result, "3"))).toBeGreaterThanOrEqual(1);
    }
    remove(folder);
  });

  test("many prompts queued at once all run, and deck still deals every line once per round", async ({ request }) => {
    const prompts = [];
    for (let seed = 0; seed < 4; seed++) prompts.push(runPrompt(request, clip("__color__", "", { seed: 1000 + seed, mode: "deck" })));
    for (let index = 0; index < 18; index++) {
      const mode = MODES[index % MODES.length];
      prompts.push(runPrompt(request, clip(`{a|b|c} __hair/style__ ${index}`, "", { seed: index, mode })));
      prompts.push(runPrompt(request, randomInt({ seed: index, seed_mode: ["random", "deck", "shuffle", "balanced", "sequential"][index % 5], min: -5, max: 5 })));
    }
    const results = await Promise.all(prompts);
    for (const result of results) expect(result.status).toBe("success");
    expect(results.slice(0, 4).map((result) => shown(result, "2")).sort()).toEqual(["blue", "green", "red", "white"]); // Seeds 1000-1003: one round.
    for (const result of results.slice(4)) {
      const value = shown(result, "2");
      if (/^-?\d+$/.test(value)) expect(Math.abs(Number(value))).toBeLessThanOrEqual(5);
      else expect(value).toMatch(/^[abc] (bob cut|long hair) \d+$/);
    }
  });

  test("every seed mode runs through the queue, the reproducible ones from the cache and the remembering ones every time", async ({ request }) => {
    const text = "{red|green|blue} {cat|dog} __color__";
    for (const mode of MODES) {
      const first = await runPrompt(request, clip(text, "", { seed: 5, mode }));
      const second = await runPrompt(request, clip(text, "", { seed: 5, mode }));
      expect(first.status, mode).toBe("success");
      expect(shown(first, "2"), mode).toMatch(/^(red|green|blue) (cat|dog) (red|blue|green|white)$/);
      if (["shuffle", "balanced", "mutate"].includes(mode)) expect(second.cached, mode).not.toContain("1");
      else {
        expect(second.cached, mode).toContain("1");
        expect(shown(second, "2"), mode).toBe(shown(first, "2"));
      }
    }
    let last = shown(await runPrompt(request, clip("{a|b|c} {x|y} {1|2|3}", "", { mode: "mutate" })), "2").split(" ");
    for (let run = 0; run < 6; run++) {
      const now = shown(await runPrompt(request, clip("{a|b|c} {x|y} {1|2|3}", "", { mode: "mutate" })), "2").split(" ");
      expect(now.filter((part, index) => part !== last[index]), `${last} -> ${now}`).toHaveLength(1); // Exactly one choice changes per run.
      last = now;
    }
    const total = 3 * 2 * 4;
    const all = new Set();
    for (let seed = 0; seed < total; seed++) all.add(shown(await runPrompt(request, clip(text, "", { seed, mode: "combinations" })), "2"));
    expect(all.size).toBe(total); // Every combination exactly once.
  });

  test("text in any script and emoji passes through the queue unchanged", async ({ request }) => {
    const cases = [
      ["портрет девушки, {рыжие|чёрные} волосы", ["портрет девушки, рыжие волосы", "портрет девушки, чёрные волосы"]],
      ["猫の写真、{赤|青}", ["猫の写真、赤", "猫の写真、青"]],
      ["🐱 + 🎲 = {✨|🔥}", ["🐱 + 🎲 = ✨", "🐱 + 🎲 = 🔥"]],
      ["مرحبا {أ|ب}", ["مرحبا أ", "مرحبا ب"]],
      ["a\u00a0b — “quotes” ‘x’ … ½ {é|ß}", ["a\u00a0b — “quotes” ‘x’ … ½ é", "a\u00a0b — “quotes” ‘x’ … ½ ß"]],
    ];
    for (const [text, possible] of cases) {
      const seen = new Set();
      for (let seed = 0; seed < 2; seed++) {
        const result = await runPrompt(request, clip(text, `не ${text}`, { seed, mode: "deck" }));
        expect(result.status, text).toBe("success");
        expect(possible, text).toContain(shown(result, "2"));
        expect(possible.map((option) => `не ${option}`), text).toContain(shown(result, "3"));
        seen.add(shown(result, "2"));
      }
      expect(seen.size, text).toBe(2); // deck: both options over two seeds.
    }
  });

  test("a big wildcard file deals quickly through the queue", async ({ request }) => {
    const file = writeFile("models/wildcards/e2e_big.txt", Array.from({ length: 50000 }, (_, index) => `line ${index}`).join("\n"));
    try {
      const started = Date.now();
      for (const mode of ["random", "deck", "shuffle", "balanced", "combinations"]) {
        const result = await runPrompt(request, clip("__e2e_big__", "", { seed: 31337, mode }));
        expect(result.status, mode).toBe("success");
        expect(shown(result, "2")).toMatch(/^line \d+$/);
      }
      expect(Date.now() - started).toBeLessThan(30_000);
    } finally {
      remove(file);
    }
  });

  test("Random Chaos keeps the orientation and the side rescale sets, through the queue", async ({ request }) => {
    for (const [size, rescale, check] of [
      ["Portrait", { rescale: "to Width/Height", "rescale.width": 1024, "rescale.height": 0 }, (w, h) => w === 1024 && h > w],
      ["Landscape", { rescale: "to Width/Height", "rescale.width": 0, "rescale.height": 768 }, (w, h) => h === 768 && w > h],
      ["Portrait", { rescale: "to longest side", "rescale.longer_side": 1536 }, (w, h) => h === 1536 && w < h],
      ["Any", { rescale: "to Width/Height", "rescale.width": 640, "rescale.height": 640 }, (w, h) => w === 640 && h === 640],
    ]) {
      for (let seed = 0; seed < 12; seed++) {
        const result = await runPrompt(request, sdxl({ resolution: "Random Chaos", "resolution.size": size, "resolution.max_aspect": 1.05, seed, multiple: 64, ...rescale }));
        expect(result.status).toBe("success");
        const [w, h] = [Number(shown(result, "2")), Number(shown(result, "3"))];
        expect(check(w, h), `${size} ${JSON.stringify(rescale)} seed ${seed}: ${w}x${h}`).toBe(true);
      }
    }
  });
});
