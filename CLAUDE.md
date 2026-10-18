# DiceForge: rules for Claude Code

DiceForge is a ComfyUI node pack: Python nodes and HTTP routes in `DiceForge/`, their frontend in `DiceForge/web/`, unit tests in `tests/`,
end-to-end tests in `e2e/` (Playwright, a real ComfyUI), QA tools in `e2e/qa/`, CI scripts in `.github/scripts/`. The README's Development
section describes the tests, the agents and the release.

## Talking with the author

- Answer in Russian. Code, comments, docs, commit messages and everything in the repository stay in English.
- The author follows the work from the Claude app: say briefly what you are doing during long steps.

## Every change

1. Make the change.
2. Add tests:
   - unit tests in `tests/` for the Python (the fixtures in `tests/conftest.py` keep everything in temporary folders);
   - end-to-end tests for the frontend, in **both node designs**: Nodes 2.0 and classic, the `for (const vue of [true, false])` blocks of
     `e2e/ui-*.spec.js`.
   - A new route goes into `ROUTES` in `tests/test_robustness.py`.
3. Update `README.md` (what users see and do) and `CHANGELOG.md` (under `[Unreleased]`: Added, Changed, Fixed or Removed), in the voice of
   the text around.
4. Before committing: `python .github/scripts/review_checks.py origin/main` (line endings, syntax, unsafe code, routes, missing tests or
   docs), or ask the `reviewer` agent. On the author's computer `python` is the
   Microsoft Store stub: `..\..\..\python_embeded\python.exe -X utf8 .github/scripts/review_checks.py origin/main` (without `-X utf8` it
   stops on a cp1251 decode error).
5. Commit to `main` with a message that says what changed for users. Keep the `Co-Authored-By` trailer Claude Code adds. Push to `main`.
6. Check CI on GitHub (the Tests workflow), and fix it until it is green.
   - **Unit tests and SonarQube Cloud:** a failed Quality Gate fails the run.
   - **Five end-to-end jobs,** left out when a push changes nothing in `DiceForge/`, `e2e/` or `tests.yml` (the `changes` job).
   - The repository is public (since 2026-10-18), so Actions minutes are free; it was private before and ran out of them.

## Checks

- **Let GitHub run the tests.** Locally, only check syntax: `python -m py_compile`, `node --check`, `bash -n`, `review_checks.py`.
- **Looking at the real thing is fine:** ComfyUI in a browser, screenshots, `e2e/qa` tools.
- **Sonar** has failed CI here before. Avoid:
  - building a path from request input (S2083): look the name up among the stored data or the files that exist instead; a regex or
    allowlist check does not satisfy it;
  - `random` outside the seeded places listed in `sonar-project.properties` (S2245): use `secrets`;
  - template literals nested in `${...}` (S4624);
  - functions harder to follow than about 15 (S3776);
  - a blocking `open()` in an `async` route handler (S7493, counted as a bug: it fails the reliability condition): read and write files
    through `run_in_executor`, as the other routes do;
  - regular expressions that can backtrack (S8786).
- **The end-to-end tests answer DiceForge's questions with `answerQuestions`** (`e2e/helpers.js`), a Playwright locator handler. It only runs
  before a locator action or a locator assertion: a question raised by a `page.evaluate` (a menu callback) and followed only by
  `expect.poll` is never answered, and the test times out.

## Code

- **Line endings:** several files are CRLF (`README.md`, `.github/workflows/tests.yml`, some `DiceForge/web` and `e2e` files). Keep each
  file's own. Editing with a script that turns CRLF into LF changes every line; `review_checks.py` catches it.
- **Read like the code around it:** whole plain sentences in comments, saying why, at the same density.
- **Reuse the helpers:**
  - `dom.js`: `element`, `addStyleOnce`, `background` for promises not awaited, `fitToContent` for panels in nodes, `askConfirm` and
    `askText` for questions (ComfyUI's dialogs; never the browser's `confirm()` or `prompt()`), `asking()` before a window's own keys;
  - `menu.js`: right-click menus, keys;
  - `window_memory.js`: what windows remember, their size;
  - `node_size.js`: node heights;
  - `move_dialog.js`: the folder picker and drag and drop onto a tree; `media.js`: Civitai pictures and videos, Blur NSFW;
  - `http_read.py`, `model_lists.py`; `model_info.json_body` for every POST body.
- **Where things are:**
  - `seed_modes.py`: the pickers every random node uses, and the seed memory (SQLite in `user/DiceForge`). Every mode gives the same result
    for the same seed.
  - `clip_text_encode_pos_neg.py`: the prompt syntax (choices, wildcards, variables, `<lora:>`) and `fill_in`, also used by Wildcards to
    Text, Danbooru Tag Enhancer and the Wildcard Browser's previews. `wildcards_api.py`: the Wildcard Browser's routes, yaml edits that keep
    comments, the trash.
  - Nodes are V3 (`io.ComfyNode`), registered in `DiceForge/__init__.py`. Modules with routes have `register_routes()`, run at import.
  - A node's preview gets its run's data from `ui={"dice_forge_…": [...]}`; the frontend keeps it in `node.properties`, so it travels with
    the workflow.
  - The prompt tools work on the text fields of `PROMPT_NODES` (`wildcards.js`). Wildcard Note is a frontend-only node
    (`wildcard_note.js`).
- `ComfyUI/AGENTS.md`, which Claude Code shows when files of ComfyUI are read, holds the rules of ComfyUI's own code, not DiceForge's.
- **Text is shown as text** (`element()`), never as HTML. Links to new tabs open with `noopener`. `.github/scripts/security_scan.py`, run by
  the unit tests, fails CI otherwise.
- **No release yet** (no `v*` tag): DiceForge has no users but its author, so breaking changes are fine. Don't add repairs for workflows or
  files of earlier versions. After the first release, the old-workflow tests (`e2e/workflows/`, `e2e/compat.spec.js`) keep them working.

## Agents

`.claude/agents`:
- **`tester`:** uses DiceForge in a browser in both designs and reports what is broken or looks wrong.
- **`reviewer`:** reviews a change before the push.
- **`comfy-watcher`:** what a newer ComfyUI breaks.
- **`compat`:** old workflows; adds a release's workflow to the corpus.
- **`security`:** routes, files, downloads, shown text.
- **`docs`:** README and CHANGELOG against the code.
- **`perf`:** speed with a lot of data.

They report and don't change the code, except `docs`, which edits the docs when asked to. Their tools work without them too (README →
Development → Agents).

## Secrets

- **Never ask for tokens or keys, and never use or keep one pasted in a conversation.** That includes `SONAR_TOKEN` and the Registry key.
- **The author adds secrets to GitHub themselves:** `SONAR_TOKEN`, and `REGISTRY_ACCESS_TOKEN` for publishing to the ComfyUI Registry.

## Running ComfyUI locally

- **This repository is meant to be cloned into `ComfyUI/custom_nodes`.** The unit tests find ComfyUI there, two folders up, or through
  `COMFYUI_PATH`. Only one copy of DiceForge may be in `custom_nodes`: two would load the nodes twice.
- **The end-to-end tests** find ComfyUI next to the repository or through `COMFYUI_PATH`, and its Python in a venv or the Windows portable
  build's `python_embeded`. They start their own ComfyUI in a temporary folder, so the author's ComfyUI and files are never touched.
- **The author's ComfyUI is the Windows portable build**, with this repository in `ComfyUI_windows_portable\ComfyUI\custom_nodes\ComfyUI-DiceForge`:
  - its Python is `..\..\..\python_embeded\python.exe` from the repository (`-m pip install pytest hypothesis` once, then `-m pytest tests`);
  - the end-to-end tests: in `e2e`, `npm ci`, `npx playwright install chromium`, then `$env:COMFYUI_PATH="..\..\.."; npx playwright test`.
- **Git keeps each file's line endings as they are** in this repository (`git config core.autocrlf false`): Git for Windows would otherwise
  convert them and show files as changed. In Git Bash, `sed -i` turns a CRLF file into LF: edit with a Python script that reads and
  writes with `newline=""`.
- **CI from here:** `gh` may not be on the PATH: `"C:\Program Files\GitHub CLI\gh.exe" run list`,
  `run view <id> --log-failed`, `run view --job <id> --log`.

## Where the work stands (October 2026)

Update this section as the steps get done, and remove it when they all are.

- **Done:** every node and window; unit and end-to-end tests in both designs, the ComfyUI contract and the old-workflow tests; the agents;
  every node id starting with `DiceForge` (`tests/test_node_ids.py` keeps it so).
- **CI is red on `main` since 2026-10-16.** The last run (`28cd3dd`, the questions in ComfyUI's dialogs) fails on these; fix them first:
  - 10 end-to-end tests whose question comes from a node menu, not a window: ✂ Selection → new wildcard, Wildcard Note's save, Prompt
    styles and KSampler presets (saving), Dice Grid (↺ a cell's run). Their `answerQuestions` never runs (see Checks).
  - Sonar's Quality Gate: S7493 in `read_yaml_file` (`wildcards_api.py`, `GET /diceforge/wildcards/yaml`); and seven S8786 regular
    expressions in `wildcards.js`.
  - The README's *On GitHub* says four end-to-end jobs; there are five.
- **Next, in this order:**
  1. **A full pass of the agents:** `tester`, `security`, `perf` (also `--scale 3`), `docs`, `comfy-watcher` against ComfyUI master. Then fix
     what they find. Known already: adding 100 nodes takes about 3 s in Nodes 2.0 and 0.6 s in the classic canvas.
  2. **What ComfyUI offers node packs and DiceForge doesn't use yet** (docs.comfy.org → Custom Nodes and Registry, read 2026-10-10):
     - `pyproject.toml`: `requires-comfyui` and a minimum `comfyui-frontend-package` in `dependencies`, since DiceForge needs the V3
       schema's DynamicCombo and the Nodes 2.0 design (find the first versions that have what it uses); `Icon` is empty, and `Banner`
       is missing. Without the minimums the Registry offers DiceForge to an old ComfyUI it doesn't work in.
     - `example_workflows/` at the repository root: workflow JSON files, each with a `.jpg` of the same name, that ComfyUI's template
       browser shows as a DiceForge section (an Anima text-to-image like the author's `Anima_DiceForge`, an SDXL one, an XY Plot).
     - Node help: `DiceForge/web/docs/<node id>.md` (and `<node id>/<locale>.md`), Markdown with pictures and video shown in ComfyUI's
       node help panel instead of the description; the README's node sections are most of it.
     - Optional: `subgraphs/` (blueprints in the subgraph browser), `locales/` (node, input and tooltip names in other languages).
  3. **The first release, 1.0.0** (it was never published):
     - fold `[Unreleased]` into the `[1.0.0]` section of the CHANGELOG;
     - the author adds `REGISTRY_ACCESS_TOKEN`;
     - tag `v1.0.0`;
     - save the release's workflow for the old-workflow tests (`node e2e/qa/snapshot.js --version 1.0.0`, README → Releasing).
  4. **After it:**
     - a weekly `comfy-watcher` run;
     - a renamed node, or one whose inputs change, gets a Node Replacement (`io.NodeReplace` registered in the extension's `on_load`,
       docs.comfy.org/custom-nodes/backend/node-replacement): the frontend offers the upgrade when it opens an old workflow and keeps
       links and values. Use it instead of hand-written repairs, with a workflow in the old-workflow corpus that shows it working.
