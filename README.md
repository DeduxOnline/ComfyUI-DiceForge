# ResolutionForge

ComfyUI nodes for setting up a generation: two resolution nodes that output `width`, `height`, `batch` and `seed` for an empty latent (both can pick the canvas size at random from a seed), their *Latent* versions that output the empty latent directly, a prompt encoder that outputs positive and negative conditioning from one node, and a prompt builder that writes consistent anime scenes as Danbooru tags.

| Node | File | Use it when |
|---|---|---|
| **SDXL Resolution List** | `ResolutionForge/sdxl_resolution_list.py` | You want the standard SDXL sizes (1024x1024, 1216x832, ...) from a fixed list. |
| **Resolution Selector (Random)** | `ResolutionForge/resolution_selector_random.py` | You want to set an aspect ratio and a megapixel target, like the core *Resolution Selector* node. |
| **SDXL Resolution List (Latent)** | `ResolutionForge/sdxl_resolution_list_latent.py` | Same as *SDXL Resolution List*, but you want the empty latent itself instead of connecting **Empty Latent Image**. |
| **Resolution Selector (Random, Latent)** | `ResolutionForge/resolution_selector_random_latent.py` | Same as *Resolution Selector (Random)*, but you want the empty latent itself. |
| **CLIP Text Encode (Positive/Negative)** | `ResolutionForge/clip_text_encode_pos_neg.py` | You want both prompts in one node instead of two *CLIP Text Encode (Prompt)* nodes. |
| **Prompt Director (Anime)** | `ResolutionForge/prompt_director.py` | You want a random but logical anime scene (outfit fits the place and weather, pose fits the framing, ...) as Danbooru tags for Illustrious or Pony, optionally written in more detail by an LLM such as Qwen3-VL. |

The resolution nodes are in the `utils` category, their *Latent* versions in `model/latent`, the prompt encoder in `model/conditioning`, and the prompt builder in `text`. All nodes use the ComfyUI V3 node schema: in the Nodes 2.0 frontend, the secondary inputs of the resolution nodes sit in the node's **Advanced** section.

## Installation

Copy the `ResolutionForge` folder into `ComfyUI/custom_nodes` and restart ComfyUI:

```sh
git clone https://github.com/DeduxOnline/unified_sdxl_res.git
cp -r unified_sdxl_res/ResolutionForge ComfyUI/custom_nodes/
```

Cloning the whole repository straight into `custom_nodes` does not work: the nodes are in the `ResolutionForge` subfolder, so ComfyUI does not find them.

`ResolutionForge/__init__.py` registers all six nodes. To install only one of them, copy that `.py` file from `ResolutionForge` straight into `ComfyUI/custom_nodes` instead. This does not work for the *Latent* nodes (they reuse the code of their base resolution node) or for *Prompt Director* (it needs its `prompt_director` data folder): install them with the whole folder.

**Requirements:** a recent ComfyUI that includes `comfy_api.latest` (the V3 node API). *Resolution Selector (Random)* also needs the resolution preview widget, which ships with the core *Resolution Selector* node. Older ComfyUI versions will not load these nodes.

## Typical use

- Connect `width`, `height` and `batch` of a resolution node to the `width`, `height` and `batch_size` inputs of **Empty Latent Image**.
- Or use a *Latent* version and connect its `latent` output straight to the `latent_image` input of **KSampler**.
- Connect the `CLIP` output of your checkpoint loader to **CLIP Text Encode (Positive/Negative)**, then its `positive` and `negative` outputs to the matching inputs of **KSampler**.
- To drive the image and the canvas size from one seed, connect the `seed` output of a resolution node to the `seed` input of **KSampler**.

## SDXL Resolution List

Node id: `UnifiedSDXLResolution`. Workflows saved with earlier versions of this node keep loading.

### Inputs

| Input | Section | Default | Description |
|---|---|---|---|
| `resolution` | main | `1024 x 1024 (1:1 Square)` | A fixed size, or one of the random options below. |
| `seed` | main | `0` | Seed for the random options. The same seed always gives the same size. |
| `multiply` | Advanced | `1.0` | Scales width and height by this factor (0.1–10). Note that 2.0 gives 4x the pixels. |
| `vae_alignment` | Advanced | `64` | Rounds width and height to the nearest multiple of this value (8–256). |
| `batch` | Advanced | `1` | Passed through to the `batch` output (1–32). |

### Outputs

| Output | Description |
|---|---|
| `width` | Width in pixels. |
| `height` | Height in pixels. |
| `batch` | The `batch` input, for the `batch_size` input of **Empty Latent Image**. |
| `seed` | The seed used for this run, the same as the node's `seed` input. For example, connect it to the `seed` input of **KSampler**. |

### Fixed sizes

| Standard | High-res |
|---|---|
| 1024 x 1024 (1:1) | 1536 x 1536 (1:1) |
| 1152 x 896 (9:7) / 896 x 1152 (7:9) | 1536 x 1152 (4:3) / 1152 x 1536 (3:4) |
| 1216 x 832 (3:2) / 832 x 1216 (2:3) | 1536 x 1024 (3:2) / 1024 x 1536 (2:3) |
| 1344 x 768 (16:9) / 768 x 1344 (9:16) | 1536 x 864 (16:9) / 864 x 1536 (9:16) |
| 1536 x 640 (21:9) / 640 x 1536 (9:21) | |

### Random options

- **Any Listed / Any High-Res Listed**: one of the standard or high-res sizes above.
- **Vertical Listed / Horizontal Listed** (and their **High-Res** versions): only portrait or only landscape sizes.
- **Random Small / Medium / Large**: a random size with up to 512², 1024² or 1536² pixels. The width varies by ±30% around the square size and the orientation is random. These options round down, so they never exceed their pixel limit before `multiply`.

### Notes

- Rounding to `vae_alignment` applies to fixed sizes too: with the default 64, 864 becomes 896. Set `vae_alignment` to 32 or lower to keep 864 exactly.
- Like any `seed` input, it gets the frontend's *control after generate* option, which is *randomize* by default, so the random options give a new size on each run. Set it to *fixed* to keep the same size.

## Resolution Selector (Random)

Node id: `ResolutionSelectorRandom`.

It works like the core ComfyUI *Resolution Selector*, using the same size calculation, and adds random aspect ratios. For fixed ratios, its output is identical to the core node's.

### Inputs

| Input | Section | Default | Description |
|---|---|---|---|
| `aspect_ratio` | main | `1:1 (Square)` | A fixed ratio, or one of the random options below. |
| `megapixels` | main | `1.0` | Target total size (0.1–16). 1.0 MP = 1024x1024 for a square. |
| `preview` | main | — | Live preview of the output size. It shows "—" for random options, because their size is only known at run time. |
| `seed` | main | `0` | Seed for the random options. By default it is randomized after each run (*control after generate*), so every run gets a new random ratio. Set it to *fixed* to repeat a result. |
| `multiple` | Advanced | `8` | Rounds width and height to the nearest multiple of this value (8–128). Use 64 for SDXL training sizes. |
| `batch` | Advanced | `1` | Passed through to the `batch` output (1–32). |
| `max_aspect` | Advanced | `2.0` | Random Chaos only: the most stretched ratio allowed (1.0–4.0). 2.0 means up to 2:1 or 1:2. |

### Outputs

| Output | Description |
|---|---|
| `width` | Width in pixels. |
| `height` | Height in pixels. |
| `batch` | The `batch` input, for the `batch_size` input of **Empty Latent Image**. |
| `seed` | The seed used for this run, the same as the node's `seed` input. For example, connect it to the `seed` input of **KSampler**. |

### Aspect ratios

1:1, 2:3, 3:2, 3:4, 4:3, 7:9, 9:7, 9:16, 16:9, 9:21, 21:9.

### Random options

- **Random Any / Random Portrait / Random Landscape**: one of the listed ratios (any, only portrait or only landscape), each equally likely.
- **Random Chaos Any / Random Chaos Portrait / Random Chaos Landscape**: any ratio up to `max_aspect`. Wide and tall ratios are equally likely.

### Notes

- The output always stays close to `megapixels`: at 1.0 MP it varies between about 0.94 and 1.06 MP because of rounding to `multiple`.
- With a large `multiple` such as 64, Random Chaos Portrait/Landscape can return a square: ratios very close to 1:1 round to one.

## Latent versions

**SDXL Resolution List (Latent)** (node id `SDXLResolutionListLatent`) and **Resolution Selector (Random, Latent)** (node id `ResolutionSelectorRandomLatent`) have exactly the same inputs as their base nodes, including the Advanced section and, for the selector, the live preview. The size is chosen the same way; `batch` sets the number of latents in the batch.

### Outputs

| Output | Description |
|---|---|
| `latent` | Empty latent batch, identical to what **Empty Latent Image** makes for this size and batch. |
| `width` | Width in pixels, for example for an upscale or hires-fix step. |
| `height` | Height in pixels. |
| `seed` | The seed used for this run, the same as the node's `seed` input. |

Like the output of **Empty Latent Image**, the latent works with any model you would use that node with: the core samplers adapt an empty latent to the model's latent format.

## CLIP Text Encode (Positive/Negative)

Node id: `CLIPTextEncodePositiveNegative`.

Works like two core *CLIP Text Encode (Prompt)* nodes sharing one CLIP model: each prompt is encoded exactly the same way, so the conditioning is identical to the core node's for the same text. On top of that, both prompts support wildcards and `{a|b}` choices, picked from a seed.

### Inputs

| Input | Section | Description |
|---|---|---|
| `clip` | main | The CLIP model used for encoding both prompts. |
| `positive` | main | The positive prompt (top text field): what the image should contain. |
| `negative` | main | The negative prompt (bottom text field): what the image should avoid. |
| `seed` | Advanced | Seed for choices and wildcards. The same seed always gives the same prompts. By default it is randomized after each run (*control after generate*); set it to *fixed* to repeat a result. |

### Outputs

| Output | Description |
|---|---|
| `positive` | Conditioning from the positive prompt. |
| `negative` | Conditioning from the negative prompt. |
| `positive_text` | The positive prompt as encoded, with choices and wildcards filled in. |
| `negative_text` | The negative prompt as encoded, with choices and wildcards filled in. |

### Prompt syntax

| Syntax | Result |
|---|---|
| `__name__` | A random line from the wildcard file `name.txt`. |
| `__folder/name__` | A random line from `folder/name.txt` inside a wildcards folder. |
| `{red\|green\|blue}` | One of the options at random. Options can be empty (`{big\|}`) and can nest (`{a\|{b\|c}}`). |
| `// ...`, `/* ... */` | Comments, removed before encoding. |

To write `{`, `}` or `|` literally, put a backslash before it: `\{`, `\}`, `\|`.

Prompt weights such as `(word:1.2)` and embeddings work as in the core node.

Lines picked from a wildcard file can themselves contain wildcards and `{a|b}` choices; they are filled in too, up to 50 levels deep (a wildcard that includes itself stops with an error instead of looping forever).

### Wildcard files

- Put wildcard files in `ComfyUI/models/wildcards`, for example `ComfyUI/models/wildcards/color.txt`. Subfolders work too: `ComfyUI/models/wildcards/styles/photo.txt` is `__styles/photo__`.
- More folders can be added with a `wildcards:` entry in ComfyUI's `extra_model_paths.yaml`.
- One option per line. Empty lines and lines starting with `#` are skipped. Files are read as UTF-8.
- A missing or empty wildcard file stops the run with an error that names the file and the wildcards folders.
- The node runs again when a wildcard file changes, even if the prompts and the seed stay the same.

Example `color.txt`:

```text
# colors for __color__
crimson red
deep {navy|royal} blue
emerald green
```

### Notes

- Choices and wildcards are filled in by the node, from its `seed`, not by the ComfyUI frontend. The saved workflow keeps the prompts with `__name__` and `{a|b}`, and the same seed gives the same result again.
- Positive and negative are filled in from the same seed, one after the other, so the same wildcard can pick different lines in each.

## Prompt Director (Anime)

Node id: `PromptDirector`.

Builds a random anime scene that makes sense, as Danbooru tags for Illustrious or Pony. The scene is filled in slot by slot, and every slot follows the ones before it:

theme → scene (1girl, 1boy or scenery) → location → time → weather → framing → hair and eyes → outfit → shoes → accessory → expression → pose → gaze → lighting

For example: at the beach the outfit is summery, in snow it is warm; weather is only added outdoors; with a portrait or upper-body framing there are no shoes and no full-body poses; the pose fits the expression and the place (reading in a library, holding an umbrella in the rain); the lighting fits the time of day and the weather.

### Inputs

| Input | Section | Description |
|---|---|---|
| `idea` | main | Optional idea, as tags or words (for example `valkyrie before a battle`). The LLM builds the scene around it; without an LLM it is added as tags. |
| `theme` | main | `fantasy`, `modern`, `school`, `cyberpunk`, `japanese`, or `random`. |
| `scene` | main | `1girl`, `1boy`, `scenery` (no people), or `random`. |
| `framing` | main | `portrait`, `upper_body`, `cowboy_shot`, `full_body`, or `random`. |
| `model` | main | `Illustrious` or `Pony`: sets the quality, rating and negative tags. |
| `rating` | main | `general` or `sensitive` (sensitive also allows outfits like swimsuits). |
| `seed` | main | Seed for every random pick and for the LLM. The same seed gives the same prompt. By default it is randomized after each run; set it to *fixed* to repeat a result. |
| `clip` | main (optional) | An LLM loaded with **Load CLIP**, such as Qwen3-VL. Without it, the prompt is built from the rules only. |
| `time`, `weather` | Advanced | Fix the time of day or the weather (`none` for no weather). Earlier slots follow: with `snow`, the location is always outdoors and not a summer place. |
| `character`, `outfit`, `expression`, `pose`, `location` | Advanced | Your own tags for that part of the scene; empty lets the node pick. Setting a character part always gives a character scene. |
| `max_length`, `temperature` | Advanced | LLM answer length (tokens) and creativity. |
| `tag_check` | Advanced | How the LLM's tags are checked against the tag library (see below): `drop unknown` (default), `keep unknown`, or `off`. |
| `tag_hints` | Advanced | Number of real Danbooru tags suggested to the LLM for each part of the scene (default 20, 0 turns it off). |

### Outputs

| Output | Description |
|---|---|
| `positive_text` | Quality and rating tags, then the scene. Connect it to the `positive` text of **CLIP Text Encode (Positive/Negative)** (or any text input). |
| `negative_text` | Negative tags for the chosen model and rating. |
| `scene` | What was picked for each slot, whether the LLM was used, and which of its tags the tag check removed and why. Connect it to **Preview as Text** to see the logic. |
| `seed` | The seed used for this run. |

### With an LLM (Qwen3-VL)

1. Load the model with **Load CLIP** (for Qwen3-VL-4B, any `type` without its own Qwen3-VL handling works, for example `stable_diffusion`) and connect it to `clip`.
2. The node sends the LLM the scene plan: fixed parts (scene, framing, time, weather and your own tags), the rule-based picks as suggestions, and your idea. The LLM answers with JSON and adds concrete details that fit.
3. Fixed parts are always kept as they are. The other parts come from the LLM answer; if the answer has no valid JSON, the node uses the rule-based scene instead, prints the answer to the console, and says so in `scene`.

The LLM is called the same way as the core **Generate Text** node, with thinking off.

### Tag library

The node uses a Danbooru tag library for more variety and to keep tags real:

- **Variety without an LLM:** some options in the scene data pick a tag from a whole Danbooru section (`pool`, see *Scene data*), for example hair details and accessories, or what the character holds (a drink at a cafe, a phone in a modern scene, a weapon with a combat outfit). Popular tags are picked more often, and only tags the rating allows.

With an LLM connected:

- **Tag ideas:** for each part of the scene, the request lists real Danbooru tags (`tag_hints`, popular tags more likely), so a small LLM picks tags the image model knows instead of inventing them.
- **Tag check** (`tag_check`) on the LLM answer:
  - aliases become the real tag (`blond hair` → `blonde hair`);
  - explicit tags are always removed, sensitive ones (swimsuits, lingerie, ...) when the rating is `general`;
  - a tag that contradicts a fixed or earlier one is removed (a second framing or hair length);
  - with `drop unknown`, tags the image model does not know are removed: tags that are not on Danbooru, or have fewer posts than the model preset's `min_post_count` (100 for Illustrious, 500 for Pony).
- The `scene` output lists every removed tag with the reason.

The library has two parts (the known tags are downloaded the first time the node needs them: when a `pool` option is picked or an LLM is connected):

- **Known tags:** Danbooru tags with post counts and aliases, up to the Illustrious v1.0 cutoff (June 2024), from [BetaDoggo/danbooru-tag-list](https://github.com/BetaDoggo/danbooru-tag-list). It is **downloaded once**, on the first run with an LLM, to `ComfyUI/models/prompt_director/library/danbooru_tags_illustrious_v1.0.csv` (2.5 MB). Without internet access, put that file there yourself; until then only the content and contradiction checks run.
- **Tag groups:** `ResolutionForge/prompt_director/tag_groups.json`, built from the Danbooru wiki's tag groups by [PBandDev/danbooru-tag-groups-scraper](https://github.com/PBandDev/danbooru-tag-groups-scraper) (MIT license, Copyright (c) 2026 PBandDev). It sorts tags into scene parts and marks sensitive and explicit tags. To rebuild it from a newer release: `python tools/build_tag_library.py tag_groups_flat.jsonl data-YYYY-MM`.

### Scene data

The rules live in `ResolutionForge/prompt_director/anime.yaml`: slots, options with their Danbooru tags, and the conditions between them (`when`, `unless`, `weight`; the file explains the fields). An option can also use `pool` to add one tag from Danbooru tag group sections (such as `"Holding Tags > Food and Drink"`; the section names are the keys of `sections` in `tag_groups.json`), and the `hints` part at the end says which sections the LLM gets tag ideas from, with the same conditions. To add your own options without editing the bundled file, put YAML files with the same layout in `ComfyUI/models/prompt_director`: their options are added to the slots with the same name. The node runs again when a data file changes; new choices in the node's dropdowns (such as a new theme) appear after restarting ComfyUI.
