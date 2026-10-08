# Changelog

All notable changes to DiceForge. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/): a new major version when a workflow made with the last one may stop working, a minor one for new
nodes and features, a patch for fixes. Each version is a [release on GitHub](https://github.com/DeduxOnline/ComfyUI-DiceForge/releases) and on the
[ComfyUI Registry](https://registry.comfy.org).

## [Unreleased]

### Added
- The windows open where they were closed: Wildcard Browser (search, ★ Favorites, the open file with its unsaved changes, scrolling), Tag Browser
  (search, type, order), syntax guide (search), model browsers (search, tag filter, order).
- The windows can be resized by their bottom-right corner and keep their size (a double-click on the title: the default size).
- Wildcard Browser: ⇩ Export zip (every wildcard, or ⇩ zip on a folder, with a card pack's yaml file); ↶ Undo of the last rename, move or
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
- A tester: `.claude/agents/tester.md`, an agent for Claude Code that tests DiceForge in a browser like a user, in both node designs, and
  reports what it finds with pictures and steps; its tools in `e2e/qa` (setup, the test server, pictures and size checks of every node).
  The browser tests check every node for empty areas and cut-off content.

### Changed
- Node heights: a node taller than what it shows (a workflow saved so, content that got smaller) is fitted again, in both designs; only
  a node with a text field, which grows with it, keeps a height the user gave it.

### Fixed
- Previews, Dice Grid's cells and LoRA Stack's list are as tall as what they show, in both designs: no more empty area under them in a
  taller node (the text fields take the extra height), and they no longer keep a height they were once given (the classic canvas grew
  them with the node, then never gave it back); a new node is no longer made taller by a preview measured before it had its width.
- Wildcard Browser: the tree takes a third of the window, the editor (or the cards) two thirds.
- Tag Browser: ↗ opens the tag's wiki page instead of its posts: on e621 for the tags of an e621 list, on Danbooru otherwise.

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
