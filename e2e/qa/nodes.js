// Every DiceForge node, looked at: in Nodes 2.0 and the classic design; new, with its advanced inputs shown and hidden again (Nodes 2.0), and loaded
// from a workflow saved 900 tall. A picture of each (e2e/qa/out/nodes/), the pictures side by side (sheet_<design>_<n>.png), and each measured
// (lib.js measure: empty areas, cut-off content), in report.json. Prints the problems and the page's errors; exits with 1 when there are any.
//   node qa/nodes.js [--design vue|classic] [--only <part of a node type>] [--tall <height>]
// Needs the e2e server running (node server.js).
const fs = require("fs");
const { ALL_NODES } = require("../ui-shared");
const { addNodes } = require("../helpers");
const { open, shot, sheet, measure, reloadTall, outPath, frames } = require("./lib");

const option = (name, fallback) => {
  const at = process.argv.indexOf(`--${name}`);
  return at > 0 ? process.argv[at + 1] : fallback;
};
const designs = option("design") ? [option("design")] : ["vue", "classic"];
const only = (option("only") ?? "").toLowerCase();
const tall = Number(option("tall", 900));
const PER_SHEET = 6;

async function lookAt(page, vue, type) {
  const looks = [];
  const look = async (id, state) => {
    await frames(page);
    looks.push({ state, file: await shot(page, id, `nodes/${vue ? "vue" : "classic"}_${type}_${state}`), ...(await measure(page, id)) });
  };
  await page.evaluate(() => window.app.graph.clear());
  const [id] = await addNodes(page, [{ type, pos: [60, 140] }]); // Below the frontend's Graph button, which would cover the node's top.
  await look(id, "new");
  const node = page.locator(`[data-node-id="${id}"]`);
  if (vue && (await node.getByText(/Show advanced inputs/).count())) {
    await node.getByText(/Show advanced inputs/).click();
    await page.waitForTimeout(300);
    await look(id, "advanced");
    await node.getByText(/Hide advanced inputs/).click();
    await page.waitForTimeout(300);
    await look(id, "hidden");
  }
  await reloadTall(page, tall);
  await look(id, `tall${tall}`);
  return looks;
}

(async () => {
  const report = [], errors = [];
  for (const design of designs) {
    const vue = design === "vue";
    const { browser, page, errors: pageErrors } = await open({ vue });
    const types = ALL_NODES.filter((type) => type.toLowerCase().includes(only));
    const rows = [];
    for (const type of types) {
      const looks = await lookAt(page, vue, type);
      report.push(...looks);
      rows.push({ title: `${design} · ${type}`, pictures: looks.map((item) => ({ label: `${item.state} · stored ${item.stored}${item.problems.length ? " · ⚠" : ""}`, file: item.file })) });
    }
    for (let start = 0; start < rows.length; start += PER_SHEET) {
      const name = `nodes/sheet_${design}_${start / PER_SHEET + 1}`;
      console.log(`sheet: ${await sheet(browser, rows.slice(start, start + PER_SHEET), name)}`);
    }
    errors.push(...pageErrors.map((error) => `${design}: ${error}`));
    await browser.close();
  }
  fs.writeFileSync(outPath("nodes", "report.json"), JSON.stringify({ report, errors }, null, 2));
  const problems = report.flatMap((item) => item.problems.map((problem) => `${item.design} ${item.type} (${item.state}): ${problem}`));
  console.log(`${report.length} looks at ${new Set(report.map((item) => item.type)).size} node types; report: ${outPath("nodes", "report.json")}`);
  console.log(problems.length ? `PROBLEMS (${problems.length}):\n  ${problems.join("\n  ")}` : "No size problems found.");
  console.log(errors.length ? `PAGE ERRORS (${errors.length}):\n  ${errors.join("\n  ")}` : "No page errors.");
  process.exitCode = problems.length || errors.length ? 1 : 0;
})().catch((error) => {
  console.error(error);
  process.exitCode = 2;
});
