# Changelog

All notable changes to DiceForge. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/): a new major version when a workflow made with the last one may stop working, a minor one for new
nodes and features, a patch for fixes. Each version is a [release on GitHub](https://github.com/DeduxOnline/ComfyUI-DiceForge/releases) and on the
[ComfyUI Registry](https://registry.comfy.org).

## [Unreleased]

### Added
- Node help: every DiceForge node's page in ComfyUI's node help panel (Node Info), with its pictures: its section of the README.
- CI: a QA tools workflow, run by hand, for a machine without Node.js: the frontend internals, the pictures and size checks of every
  node in both designs, and the times with a lot of data, on any ComfyUI commit (master by default), kept as the `qa-out` artifact.
- Wildcard Browser: yaml wildcards are edited, no longer read-only. A yaml file is one row of the tree, opened whole in the lines view and
  saved as written (comments too); in the cards view its row shows its cards, which are edited on the card (🖊), renamed, moved, deleted with
  ↶ Undo and added (＋ New card) in their yaml file, keeping its comments and layout. 🔁 Replace changes yaml wildcards too.
- Wildcard Browser: 🂠 Card per line, a yaml card of several lines as a card per line with its own picture, and the A1111 Wildcard Gallery's
  picture places (cards/POSES/sitting.jpeg, POSES/standing/[0].jpeg for a line).
- Wildcard Note (DiceForge/utils): a note for a wildcard's lines, with the prompt fields' tools; 💾 Save to WildCard adds its new lines to the
  wildcard file picked in its list (txt or yaml), puts them in place of the file's lines, or makes a new file.
- The windows open where they were closed: Wildcard Browser (search, ★ Favorites, the open file with its unsaved changes, scrolling), Tag Browser
  (search, type, order, scrolling), syntax guide (search), model browsers (search, tag filter, order, scrolling).
- The windows can be resized by their bottom-right corner and keep their size (a double-click on the title: the default size).
- Wildcard Browser: ⇩ Export zip (every wildcard, or ⇩ Export zip in a folder's menu, with a card pack's yaml file); ↶ Undo of the last rename, move or
  delete (deleted files wait in a trash folder, the last 50).
- Wildcard Browser: a right-click menu (or ⋯) on files and folders with every action, so the rows keep only ☆ and + Add; 🎲 Preview picks
  shows what runs would put in for a wildcard or a folder.
- Model browsers: ↶ Undo of a rename, move or delete (deleted models wait in models/.diceforge_trash until ComfyUI restarts, the last 10).
- Tag Browser: a basket of picked tags, put into the prompt (or the negative one) all at once.
- Wildcard Browser: ⚠ on files that use wildcards that don't exist, and ⚠ Broken to show only them; 🔁 Replace in every file, after a preview
  (offered after a rename: the old name in the files that use it); 🧹 remove duplicate and empty lines, 🔤 sort a file's lines.
- Tag Browser: ✓ on tags already in a prompt (not added twice); 🔗 related tags from Danbooru.
- Model browsers: a right-click menu on cards; ⧉ Duplicates (the same file, by its hash); ⇆ Compare two side by side.
- The keyboard in the browsers: / to the search; ↑ ↓ Enter in the Wildcard and Tag Browsers; Delete, F2 and the menu key on files and cards.
- ? (or ⌨) in each window shows its keys.
- Wildcard Browser: ⇦ Prompt as a line adds the node's prompt to the open file as a new line (one more option of the wildcard).
- ✂ Selection → new wildcard… (the prompt node's menu): the selected part of a prompt becomes a wildcard, and __name__ takes its place.
- Model browsers: 🆕 Updates shows the models with a newer version on Civitai, and a card's menu downloads it next to the old one (then offers
  to delete the old one); Largest first in the sort; the tree shows each folder's size.
- Agents for Claude Code (`.claude/agents`), each with its tools in this repository (README → Development → Agents):
  - `tester`: tests DiceForge in a browser like a user, in both node designs, and reports what it finds with pictures and steps
    (`e2e/qa`: setup, the test server, pictures and size checks of every node).
  - `reviewer`: reviews a change before it is pushed (`.github/scripts/review_checks.py`: line endings, routes left out of the robustness
    tests, what Sonar flags, missing tests and docs).
  - `comfy-watcher`: what a newer ComfyUI changes in the parts DiceForge relies on (`e2e/contract.spec.js`, `e2e/qa/internals.js`).
  - `compat`: workflows of earlier versions keep their nodes, values and prompt (`e2e/workflows`, `e2e/qa/compat.js`, `e2e/qa/snapshot.js`).
  - `security`: the routes, files, downloads and shown text, tried on the test server (`.github/scripts/security_scan.py`).
  - `docs`: the README and CHANGELOG follow the code (`tests/test_docs.py`).
  - `perf`: times with thousands of wildcards, LoRAs and tags (`e2e/qa/perf.js`).
- `CLAUDE.md`: the project's rules for Claude Code sessions, so a new one (also on the author's computer) works the same way.
- New checks in CI: every node is checked for empty areas and cut-off content; the ComfyUI internals DiceForge relies on; workflows saved
  with published releases (from the first one on) open with every value; the README names every node, input and output, and its links and pictures work; code that is never
  allowed (HTML built from text, eval, unsafe yaml, a shell, pickle).
- Anima NAG (DiceForge/sampling): Normalized Attention Guidance for Anima, so the negative prompt works with a Turbo LoRA at CFG 1 and removes
  what CFG alone leaves in at a higher CFG. It uses KSampler's negative prompt and costs almost nothing above CFG 1. ComfyUI's own NAG node
  doesn't change Anima.

### Changed
- Node help: short pages for the side panel, each node's own: its description, picture, inputs and outputs (advanced ones apart)
  with their tooltips, and a link to its README section. Load VAE + Decode + Save and VAE Decode + Save got a description.
- Every node id starts with DiceForge, so no other node pack can take a DiceForge node's place in a workflow (ComfyUI-RuiquNodes has a
  VAEDecodeSave): `SDXLResolutionListLatent` is now `DiceForgeSDXLResolutionList`, `ResolutionSelectorRandomLatent`
  `DiceForgeResolutionSelector`, `CLIPTextEncodePositiveNegative` `DiceForgeCLIPDualTextEncode`, `LoadVAEDecodeSave`
  `DiceForgeLoadVAEDecodeSave`, `VAEDecodeSave` `DiceForgeVAEDecodeSave` and `LoadDiffusionModelCLIP` `DiceForgeLoadDiffusionModelCLIP`. The
  names in the menus stay the same; workflows saved with the old ids show these nodes as missing.
- Node heights: a node taller than what it shows (a workflow saved so, content that got smaller) is fitted again, in both designs; only
  a node with a text field, which grows with it, keeps a height the user gave it.
- Wildcard Browser: the tree takes a third of the window, the editor (or the cards) two thirds.
- Tag Browser: ↗ opens the tag's wiki page instead of its posts: on e621 for the tags of an e621 list, on Danbooru otherwise.
- CI: the end-to-end tests run when a change can affect them (the node pack, the end-to-end tests or the test workflow); a change to the
  docs, the unit tests or the agents runs the unit tests alone. The weekly, manual and release runs always have them.
- CI: the workflows run on Ubuntu 24.04 instead of the newest Ubuntu, so a new runner image doesn't change the tests' system without a
  commit; both workflows use the same versions of the GitHub actions, so Dependabot can update them again.
- CI: the end-to-end tests pass with ComfyUI's frontend 1.55 too: they show a node before looking for its panel, click the canvas away
  from the minimap, and give Dice Grid pure colors (the Nodes 2.0 color picker rounds others).
- CI: the tests run against ComfyUI of 2026-10-23 (`bc5f880`, frontend 1.57) instead of 2026-09-25, and with Playwright 1.64. Chromium
  and the Ubuntu packages it needs are kept between runs, so a slow Ubuntu mirror no longer adds ten minutes to an end-to-end job.
- DiceForge asks for ComfyUI 0.38.0 or newer with its frontend 1.53.6 or newer (the first that pass every test), so ComfyUI Manager and
  the Registry don't offer it to an older ComfyUI, and it has an icon there.
- The Wildcard Browser's code is in modules of its own (the window, its editor, Find and replace), apart from the prompt fields' tools.
- Messages of Prompt styles and Sampler presets stay as long as the others (5 s). The frontend asks the server and shows messages through
  one helper (`comfy.js`), and the server's routes share theirs (`routes.py`).
- CI: a manual run can test a ComfyUI from before 2026-09-21 too (it installs torchaudio for CPU). The frontend's pure functions (the
  prompt highlight, sampler names from a picture, styles, presets for a model, tags, Clean up) have fast unit tests, and four end-to-end
  tests wait for what they check instead of a fixed time.

### Removed
- CLIP Dual Text Encode: the preview of the last run's prompts under the inputs. The prompts as encoded are in 🕘 Prompt history, whose
  entries now also show what the run noted next to the seed (combination N of M, the LoRAs of `<lora:...>` tags).
- Each node module's own ComfyUI entry point: ComfyUI only loads the package's, and a test checks that it lists every node.
- The repairs of workflows and files of earlier versions, while DiceForge has no users but its author: SDXL Resolution List's old scale
  number and resolution list, Resolution Selector without rescale, unknown seed modes and the old vae_alignment input on loading; CLIP Dual
  Text Encode's links of workflows saved when model was its last output; Danbooru Tag Enhancer's results saved before several posts; Model
  info's lookup again of data saved before the images' generation data; the seed memory's move from ResolutionForge (and the README's
  section on updating from it).

### Fixed
- CLIP Dual Text Encode: the prompt history no longer goes into the workflow saved in the images a run makes, which handed every earlier
  prompt to whoever got a picture; the workflow itself keeps it.
- A DiceForge node the user made taller by dragging its corner keeps that height after a reload, and when its preview or list
  changes; before, it was fitted back to its content (in Nodes 2.0, to its inputs).
- Wildcard Note: its badge and the node library name DiceForge as its source instead of frontend_only, and it has a description.
- Wildcard Browser: + New file named like an existing one in other upper and lower case (`Color` next to `color.txt`) no longer writes
  over its lines on Windows and macOS: it is refused as taken.
- Wildcard Browser: ⇪ Import zip leaves out a damaged file of the zip (and one whose folder name ends in a space or dot) instead of
  stopping half-way with part of the zip unpacked.
- Model info, the model browsers' previews and LoRA Stack's base model check answer "not found" for a name ComfyUI can't look up (a path
  on another drive, a network path, `con`), instead of a server error; LoRA Stack presets and model renames refuse Windows device names
  (`con`, `nul`, `com1`), which wrote to the device instead of a file.
- XY Plot: a number too big for a float (`1e999`) or a range too long to count says so, instead of a server error.
- Danbooru Tag Enhancer and the Civitai lookups read at most 16 MB of a site's answer.
- Links and pictures from outside data (Civitai's and Danbooru's answers, the Danbooru posts a shared workflow carries) open only web
  addresses: a `javascript:` link in a workflow from someone else could run a script in ComfyUI's page when clicked.
- Wildcards: a yaml file nested very deep no longer breaks every wildcard (the Wildcard Browser, the autocomplete and every run with a
  wildcard failed): it is skipped with a warning, like an invalid one. Yaml aliases (`*name`) are not read, since a few hundred bytes of
  them stand for millions of wildcards; a file with them is skipped too.
- Wildcards and variables that use another one twice, nested deep, stop with an error after 100,000 fill-ins or a million characters,
  instead of a run that never ends; each variable is filled in once.
- XY Plot: every cell of ▶ Queue gets the same seed. The frontend gave the node's `seed` a *control after generate* (randomize), which
  changed it after each cell; it has none now.
- README: what Load Diffusion Model + CLIP has under its advanced inputs, how many downloads run at once, which test files there are, and
  sentences about repairs of earlier versions that are gone.
- ComfyUI keeps answering while DiceForge's windows read and write files: the Wildcard Browser (its list, files, yaml files, pictures,
  renames, deletes), Model info, the model browsers' previews and favorites, LoRA Stack presets, Dice Grid's cells, XY Plot's preview of a
  LoRA axis and the Civitai key do their file work beside the server instead of in it, so a big wildcard collection no longer holds up other
  requests and the progress of a run.
- Wildcard Browser: stars clicked on several files in a row are all kept, and changes to the wildcard files made at the same moment no
  longer undo each other.
- Model info: a star or notes saved while the model is being looked up on Civitai are kept when the lookup finishes.
- LoRA Stack: a preset file that can't be read says why, instead of saying there is no such preset.
- The questions of DiceForge's windows (a name, a confirmation) are ComfyUI's own dialogs instead of the browser's: they work in ComfyUI
  Desktop (which has no prompt()) and in browsers that don't show the browser's own, where → yaml, delete, rename and new file did nothing.
- Wildcard Browser: opening another file asks before the open file's unsaved changes are dropped.
- README: the inputs and outputs it didn't name yet (Wildcards to Text's `seed`, XY Plot's axes, Variation Seed's `variation_seed`, Danbooru
  Tag Enhancer's `include_general` and `position`, the utility nodes' inputs and outputs).
- Previews, Dice Grid's cells and LoRA Stack's list are as tall as what they show, in both designs: no more empty area under them in a
  taller node (the text fields take the extra height), and they no longer keep a height they were once given (the classic canvas grew
  them with the node, then never gave it back); a new node is no longer made taller by a preview measured before it had its width.

## [1.0.0] - 2026-10-03

The first release on the ComfyUI Registry: install DiceForge from ComfyUI Manager, or with `comfy node install comfyui-diceforge`.

### Nodes
- **SDXL Resolution List** and **Resolution Selector (Random)**: SDXL sizes and aspect ratios, fixed or random (listed groups and
  Random Chaos), with rescale modes (by percentage, to width/height, to the longest side) and live previews.
- **Wildcards to Text**: one prompt with the same syntax and seed modes, filled in, out as text.
- **CLIP Dual Text Encode (Wildcards, LoRA)**: positive and negative prompts in one node, with `{a|b}` choices, weights, counts and locks, `__wildcards__` (text and
  YAML files), `${variables}`, comments, `<lora:name:weight>` tags, and the seed modes; also a text-only prompt builder for other encoders.
- **Random Int**, **Random Float**, **Random Sampler**: numbers and sampler/scheduler pairs by the seed modes.
- **Random LoRA**, **Random Checkpoint**, **Random Diffusion Model**, **Random VAE**, **Random Image**: files of a folder picked by the seed modes.
- **LoRA Stack**: several LoRAs in one node with random strengths, groups that take turns, trigger words and base model checks; presets.
- **Dice Grid**: the images of a series in a labeled grid (XY grids too), saved when finished; star the best cells and keep them at full size with
  their workflow.
- **XY Plot**: an X/Y comparison of seed, steps, CFG, sampler, scheduler, LoRA, LoRA strength, denoise or variation seed/strength, every cell
  queued with one button.
- **HiresFix (Load VAE)**: as Easy-Use's HiresFix with the VAE from a list: upscale model, rescale, preview or save, encode.
- **Danbooru Tag Enhancer**: adds the tags of random Danbooru, e621 or Safebooru posts (a source list) that have the prompt's tags, new ones on every run (random) or the same
  ones again (fixed, from post_ids), with the posts' pictures on the node; any rating or mix of ratings (general to explicit); several posts at once, wildcards in the tags, switches for
  appearance, clothes, background and people-count tags (1girl, 2boys, solo…), `*` patterns in exclude (`*censor*`), and an optional prompt
  input (quality tags) that goes first without being searched.
- **Variation Seed**: variations of a picture, as A1111's variation seed, for every model with the plain KSampler.
- **Load VAE + Decode + Save**, **VAE Decode + Save** (with Easy-Use's image_output choice and a vae output), **Load Diffusion Model + CLIP**.

### Seed modes
- `random`, `deck`, `shuffle`, `balanced`, `sequential`, `combinations` and `mutate`; every mode gives the same result for the same seed, so a
  picture can be made again from its seed.

### Prompts
- Wildcard Browser (create, edit with line numbers and syntax highlighting, rename, move, delete, favorites, folders), and a cards view with
  pictures for yaml card packs (🖼 adds a card's example picture), txt ⇄ yaml conversion of a file or folder with the same names, the autocomplete in its editor too, + on a line to put it in the prompt, search by lines, zip import of card packs, and `__` autocomplete; `<lora:` autocomplete.
- Danbooru / e621 tag autocomplete and Tag Browser, with downloadable tag lists.
- Prompt styles (A1111's `styles.csv`) with built-in quality styles for Illustrious, NoobAI and Anima.
- Syntax highlighting, a preview of the prompts as encoded, a prompt history window with each run's images, and a syntax guide.

### Models
- LoRA, Checkpoint, Diffusion Model, Text Encoder and VAE Browsers: cards with Civitai previews, tags, counts and newer versions; folders,
  search, filters, favorites, batch actions; find and download on Civitai (Anima among the base models), rename, move, delete; a Blur NSFW
  switch, and videos that play with ▶.
- Model info: what Civitai knows about a file (by its hash), example images with how they were made and **Use these settings**, your own notes.
- KSampler presets for Anima, Illustrious and NoobAI (eps and v-pred), with Auto by the connected model, and your own.

[Unreleased]: https://github.com/DeduxOnline/ComfyUI-DiceForge/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/DeduxOnline/ComfyUI-DiceForge/releases/tag/v1.0.0
