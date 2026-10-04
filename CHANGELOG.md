# Changelog

All notable changes to DiceForge. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and versions follow
[Semantic Versioning](https://semver.org/): a new major version when a workflow made with the last one may stop working, a minor one for new
nodes and features, a patch for fixes. Each version is a [release on GitHub](https://github.com/DeduxOnline/ComfyUI-DiceForge/releases) and on the
[ComfyUI Registry](https://registry.comfy.org).

## [Unreleased]

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
- **Danbooru Tag Enhancer**: adds the tags of random Danbooru posts that have the prompt's tags, new ones on every run (random) or the same
  ones again (fixed, from post_ids), with the posts' pictures on the node; several posts at once, wildcards in the tags, switches for
  appearance, clothes, background and people-count tags (1girl, 2boys, solo…), `*` patterns in exclude (`*censor*`), and an optional prompt
  input (quality tags) that goes first without being searched.
- **Variation Seed**: variations of a picture, as A1111's variation seed, for every model with the plain KSampler.
- **Load VAE + Decode + Save**, **VAE Decode + Save** (with Easy-Use's image_output choice and a vae output), **Load Diffusion Model + CLIP**.

### Seed modes
- `random`, `deck`, `shuffle`, `balanced`, `sequential`, `combinations` and `mutate`; every mode gives the same result for the same seed, so a
  picture can be made again from its seed.

### Prompts
- Wildcard Browser (create, edit with line numbers and syntax highlighting, rename, move, delete, favorites, folders), and a cards view with
  pictures for yaml card packs and `__` autocomplete; `<lora:` autocomplete.
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
