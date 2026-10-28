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
   the text around. A node's help page (`DiceForge/web/docs/<node id>.md`) is written from its schema (description, tooltips) and its
   README section (picture, link): after a change to either, write the pages again with `DICEFORGE_WRITE_NODE_DOCS=1 python -m pytest tests/test_node_docs.py` (CI fails while they differ). What a node has besides its inputs (buttons, panels, menu tools, warnings) goes in `NOTES` there. Screenshots
   are in `DiceForge/web/docs/images`, for both.
4. Before committing: `python .github/scripts/review_checks.py origin/main` (line endings, syntax, unsafe code, routes, missing tests or
   docs), or ask the `reviewer` agent. On the author's computer `python` is the
   Microsoft Store stub: `..\..\..\python_embeded\python.exe -X utf8 .github/scripts/review_checks.py origin/main` (without `-X utf8` it
   stops on a cp1251 decode error).
5. Commit to `main` with a message that says what changed for users. Keep the `Co-Authored-By` trailer Claude Code adds. Push to `main`.
6. Check CI on GitHub (the Tests workflow), and fix it until it is green.
   - **Unit tests and SonarQube Cloud:** a failed Quality Gate fails the run.
   - **Five end-to-end jobs,** left out when a push changes nothing in `DiceForge/`, `e2e/` or `tests.yml` (the `changes` job).
   - The repository is public (since 2026-10-18), so Actions minutes are free; it was private before and ran out of them.
   - The jobs run on `ubuntu-24.04`, not `ubuntu-latest`: a move to a newer Ubuntu is a commit of its own. Keep each action at one version
     in both workflows: Dependabot updates them as one group and fails ("No files changed!") when they differ.
   - The tested ComfyUI is a pinned commit (`COMFYUI_REF` in `tests.yml`, three places). Move it to a master commit the weekly or a manual
     run has passed with.

## Checks

- **Let GitHub run the tests.** Locally, only check syntax: `python -m py_compile`, `node --check`, `bash -n`, `review_checks.py`.
- **Looking at the real thing is fine:** ComfyUI in a browser, screenshots, `e2e/qa` tools.
- **Sonar** has failed CI here before. Avoid:
  - building a path from request input (S2083): look the name up among the stored data or the files that exist instead; a regex or
    allowlist check does not satisfy it;
  - `random` outside the seeded places listed in `sonar-project.properties` (S2245): use `secrets`;
  - template literals nested in `${...}` (S4624);
  - functions harder to follow than about 15 (S3776);
  - a blocking `open()` in an `async` route handler (S7493, counted as a bug: it fails the reliability condition). Every route does its
    file work (reading, writing, listing, `wildcard_index`) through `in_thread` (`routes.py`), also when it is a call away, which
    Sonar misses; `tests/test_event_loop.py` fails on a file touched on the event loop. In threads two requests run at once, so a
    read-modify-write of a shared file holds its module's lock (`wildcards_api.one_at_a_time`, `model_info.INFO_CHANGES`, and
    `index_lock` for the wildcard index);
  - regular expressions that can backtrack (S8786).
- **The end-to-end tests answer DiceForge's questions with `answerQuestions`** (`e2e/helpers.js`): call it before the question is asked.
  It watches the page in the background (one watcher per page; a later call gives it new answers), because a Playwright locator handler
  only runs before a locator action, and a question from a node menu followed by `expect.poll` was never answered. An answer that fails
  fails the test at its end.
- **Wait for a state, never read it once:** `locator.textContent()` returns what is there now (an empty label while a window still loads);
  `expect(...).toHaveText` waits. `wildcardMode` (`e2e/ui-shared.js`) switches the Wildcard Browser's mode that way. After a change the
  canvas has to draw, `drawn(page)` (`e2e/helpers.js`). A fixed `waitForTimeout` only where nothing can be waited for: a check that
  nothing happens (a value kept, no file written), a loop that polls, a picture settling before a screenshot.
- **A pure frontend function gets a unit test** in `tests/test_frontend_functions.py`: `js_source` takes its definition (and the
  constants it uses) from `web/` and runs it in Node.js, which CI has. Locally the test is skipped without Node.js.

## Node design

DiceForge nodes should feel like ComfyUI's own (https://docs.comfy.org/basic-concepts/nodes); the author asks to stay inside that design.

- **A node is a function:** typed inputs and widgets, its work, typed outputs. Its body holds inputs and parameters. Before adding a panel
  in a node (a DOM widget), see whether a menu entry, a window, an output or a tooltip does the job: the last run's prompts under CLIP
  Dual Text Encode were removed for that (2026-10-23; they are in 🕘 Prompt history). The panels there now (Random Image, LoRA Stack, Dice
  Grid) are the node's own work; change them only when the author asks (LoRA Stack's rows: a switch, the strength, a ⋯ menu for the rest,
  group headers; 2026-10-28). Danbooru Tag Enhancer and XY Plot keep one row (the last run, the plot and its next cell), and the rest
  opens in a window from the node's menu; XY Plot runs with ComfyUI's Run (2026-10-28).
- **Core types on the links** (`MODEL`, `CLIP`, `VAE`, `CONDITIONING`, `LATENT`, `IMAGE`, `MASK`, `INT`, `FLOAT`, `STRING`, `BOOLEAN`, and `COMBO` for a list
  input such as KSampler's sampler), so the colors and connections are the ones users know. No look-alike types of our own.
- **The user owns the look:** title, color and size. A node's height is fitted only by `node_size.js`, which keeps a height the user
  dragged (it records the height it set in `properties.dice_forge_height`; another one is the user's).
- **Menus:** extra tools go in the node's right-click menu (`getNodeMenuItems`) or a window it opens, after the core items (color, title,
  clone, mode). Nothing duplicates the selection toolbox (color, bypass, lock, delete).
- **Modes:** a node runs when its inputs change, so a random node says when it must run again (`fingerprint_inputs`). Bypass passes
  inputs to outputs of the same type: loader-like nodes (LoRA Stack: `model`, `clip`) stay usable bypassed (`e2e/ui-nodes.spec.js` checks the model nodes).
- **Workflows people get** (templates, examples) use only core and DiceForge nodes, so nothing shows as missing.

## Code

- **Line endings:** several files are CRLF (`README.md`, `.github/workflows/tests.yml`, some `DiceForge/web` and `e2e` files). Keep each
  file's own. Editing with a script that turns CRLF into LF changes every line; `review_checks.py` catches it.
- **Read like the code around it:** whole plain sentences in comments, saying why, at the same density.
- **Reuse the helpers:**
  - `dom.js`: `element`, `addStyleOnce`, `background` for promises not awaited, `fitToContent` for panels in nodes, `askConfirm` and
    `askText` for questions (ComfyUI's dialogs; never the browser's `confirm()` or `prompt()`), `asking()` before a window's own keys;
  - `comfy.js`: `request` for a DiceForge route's JSON (its text as the error), `toast(severity, summary, detail)`;
  - `menu.js`: right-click menus, keys;
  - `window_memory.js`: what windows remember, their size;
  - `node_size.js`: node heights;
  - `move_dialog.js`: the folder picker and drag and drop onto a tree; `media.js`: Civitai pictures and videos, Blur NSFW;
  - `http_read.py`, `model_lists.py`; `routes.py`: `json_body` for every POST body, `in_thread` for a route's file work.
- **The timers in nodes stay** (a node's preview watching its `properties`, the prompt highlight's scan): each compares a kept key and
  draws only on a change, and they see a change from anywhere (a loaded workflow, a test, another extension), which hooks would miss.
  Measured slowness with hundreds of nodes is the frontend's (the `perf` agent, 2026-10-23).
- **Where things are:**
  - `seed_modes.py`: the pickers every random node uses, and the seed memory (SQLite in `user/DiceForge`). Every mode gives the same result
    for the same seed.
  - `clip_text_encode_pos_neg.py`: the prompt syntax (choices, wildcards, variables, `<lora:>`) and `fill_in`, also used by Wildcards to
    Text, Danbooru Tag Enhancer and the Wildcard Browser's previews. `wildcards_api.py`: the Wildcard Browser's routes, yaml edits that keep
    comments, the trash.
  - Nodes are V3 (`io.ComfyNode`), registered in `DiceForge/__init__.py` alone (`tests/test_node_ids.py` checks it lists every node). Modules with routes have `register_routes()`, run at import.
  - A node's preview gets its run's data from `ui={"dice_forge_…": [...]}`; the frontend keeps it in `node.properties`, so it travels with
    the workflow.
  - The prompt tools work on the text fields of `PROMPT_NODES` (`wildcards.js`, also the autocomplete and the wildcard list). Wildcard
    Note is a frontend-only node (`wildcard_note.js`). The Wildcard Browser window is `wildcard_browser.js`, with its editor
    (`wildcard_editor.js`) and Find and replace (`wildcard_replace.js`); its cards mode stays in the window, which shares their state.
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
Development → Agents). The author's computer has no Node.js: run `e2e/qa` there through the *QA tools* workflow (`qa.yml`,
`gh workflow run qa.yml -f comfyui_ref=master`) and read its `qa-out` artifact (`gh run download <id>`).

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
  every node id starting with `DiceForge` (`tests/test_node_ids.py` keeps it so); the first full pass of the agents against ComfyUI
  master (2026-10-23) and the fixes of what they found. Left from it: Nodes 2.0 is slow with hundreds of nodes (300 take about 7 s,
  the frontend's), and POST routes still take any content type (ComfyUI's own check stops other sites' pages).
- **CI is green on `main` again since 2026-10-18** (`8e1f7c7`), after being red from 2026-10-16.
- **Next, in this order:**
  1. **What ComfyUI offers node packs and DiceForge doesn't use yet** (docs.comfy.org → Custom Nodes and Registry, read 2026-10-10):
     - Done: `pyproject.toml` asks for ComfyUI 0.38.0 and frontend 1.53.6 (the first that pass a manual Tests run; 0.36.0 fails on the
       resolution preview), and has an `Icon` (`docs/icon.png`). A newer minimum: check it the same way, with `comfyui_ref`. `Banner`
       (21:9) is still missing.
     - `example_workflows/` at the repository root: workflow JSON files, each with a `.jpg` of the same name, that ComfyUI's template
       browser shows as a DiceForge section (an Anima text-to-image like the author's `Anima_DiceForge`, an SDXL one, an XY Plot).
     - Done: node help, `DiceForge/web/docs/<node id>.md` written from the schema and the README (`tests/test_node_docs.py`). Left: pages in other
       languages (`<node id>/<locale>.md`).
     - Optional: `subgraphs/` (blueprints in the subgraph browser), `locales/` (node, input and tooltip names in other languages).
  2. **The first release, 1.0.0** (it was never published):
     - fold `[Unreleased]` into the `[1.0.0]` section of the CHANGELOG;
     - the author adds `REGISTRY_ACCESS_TOKEN`;
     - tag `v1.0.0`;
     - save the release's workflow for the old-workflow tests (`node e2e/qa/snapshot.js --version 1.0.0`, README → Releasing).
  3. **After it:**
     - a weekly `comfy-watcher` run;
     - a renamed node, or one whose inputs change, gets a Node Replacement (`io.NodeReplace` registered in the extension's `on_load`,
       docs.comfy.org/custom-nodes/backend/node-replacement): the frontend offers the upgrade when it opens an old workflow and keeps
       links and values. Use it instead of hand-written repairs, with a workflow in the old-workflow corpus that shows it working.
