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
   docs), or ask the `reviewer` agent.
5. Commit to `main` with a message that says what changed for users. Keep the `Co-Authored-By` trailer Claude Code adds. Push to `main`.
6. Check CI on GitHub (the Tests workflow), and fix it until it is green.
   - **Unit tests and SonarQube Cloud:** a failed Quality Gate fails the run.
   - **Five end-to-end jobs.**

## Checks

- **Let GitHub run the tests.** Locally, only check syntax: `python -m py_compile`, `node --check`, `bash -n`, `review_checks.py`.
- **Looking at the real thing is fine:** ComfyUI in a browser, screenshots, `e2e/qa` tools.
- **Sonar** has failed CI here before. Avoid:
  - building a path from request input (S2083): look the name up among the stored data or the files that exist instead; a regex or
    allowlist check does not satisfy it;
  - `random` outside the seeded places listed in `sonar-project.properties` (S2245): use `secrets`;
  - template literals nested in `${...}` (S4624);
  - functions harder to follow than about 15 (S3776).

## Code

- **Line endings:** several files are CRLF (`README.md`, `.github/workflows/tests.yml`, some `DiceForge/web` and `e2e` files). Keep each
  file's own. Editing with a script that turns CRLF into LF changes every line; `review_checks.py` catches it.
- **Read like the code around it:** whole plain sentences in comments, saying why, at the same density.
- **Reuse the helpers:**
  - `dom.js`: `element`, `addStyleOnce`, `background` for promises not awaited, `fitToContent` for panels in nodes;
  - `menu.js`: right-click menus, keys;
  - `window_memory.js`: what windows remember, their size;
  - `node_size.js`: node heights;
  - `http_read.py`, `model_lists.py`.
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
  `COMFYUI_PATH`.
- **The end-to-end tests** find ComfyUI next to the repository or through `COMFYUI_PATH`, and its Python in a venv or the Windows portable
  build's `python_embeded`. They start their own ComfyUI in a temporary folder, so the author's ComfyUI and files are never touched.
