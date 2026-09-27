# ResolutionForge

ComfyUI nodes for setting up a generation: two resolution nodes that output an empty latent of the chosen size (both can pick the size at random from a seed), and a prompt encoder that outputs positive and negative conditioning from one node.

The anime prompt builder *Prompt Director* now lives in its own repository: [DeduxOnline/ComfyUI-PromptDirector](https://github.com/DeduxOnline/ComfyUI-PromptDirector).

| Node | File | Use it when |
|---|---|---|
| **SDXL Resolution List (Latent)** | `ResolutionForge/sdxl_resolution_list_latent.py` | You want the standard SDXL sizes (1024x1024, 1216x832, ...) from a fixed list. |
| **Resolution Selector (Random, Latent)** | `ResolutionForge/resolution_selector_random_latent.py` | You want to set an aspect ratio and a megapixel target, like the core *Resolution Selector* node. |
| **CLIP Text Encode (Positive/Negative)** | `ResolutionForge/clip_text_encode_pos_neg.py` | You want both prompts in one node instead of two *CLIP Text Encode (Prompt)* nodes. |

The resolution nodes are in the `model/latent` category and the prompt encoder in `model/conditioning`. All nodes use the ComfyUI V3 node schema: in the Nodes 2.0 frontend, the secondary inputs sit in the node's **Advanced** section.

Earlier versions also had *SDXL Resolution List* and *Resolution Selector (Random)*, which output `width`, `height` and `batch` for **Empty Latent Image**. They were removed: use the *Latent* nodes, which take the same inputs. Workflows saved with the removed nodes need them replaced.

## Installation

Copy the `ResolutionForge` folder into `ComfyUI/custom_nodes` and restart ComfyUI:

```sh
git clone https://github.com/DeduxOnline/unified_sdxl_res.git
cp -r unified_sdxl_res/ResolutionForge ComfyUI/custom_nodes/
```

Cloning the whole repository straight into `custom_nodes` does not work: the nodes are in the `ResolutionForge` subfolder, so ComfyUI does not find them.

`ResolutionForge/__init__.py` registers all three nodes. `sdxl_resolution_list.py` and `resolution_selector_random.py` hold the size logic of the resolution nodes, so install those with the whole folder. The prompt encoder can also be installed alone: copy `clip_text_encode_pos_neg.py` straight into `ComfyUI/custom_nodes`.

**Requirements:** a recent ComfyUI that includes `comfy_api.latest` (the V3 node API). *Resolution Selector (Random, Latent)* also needs the resolution preview widget, which ships with the core *Resolution Selector* node. Older ComfyUI versions will not load these nodes. *SDXL Resolution List (Latent)* uses the same preview widget, fed by a small frontend extension in `ResolutionForge/web` that is loaded with the folder.

## Typical use

- Connect the `latent` output of a resolution node to the `latent_image` input of **KSampler**.
- Connect the `CLIP` output of your checkpoint loader to **CLIP Text Encode (Positive/Negative)**, then its `positive` and `negative` outputs to the matching inputs of **KSampler**.
- To drive the image and the canvas size from one seed, connect the `seed` output of a resolution node to the `seed` input of **KSampler**.

## SDXL Resolution List (Latent)

Node id: `SDXLResolutionListLatent`.

The resolution is a nested list: first pick a group in `resolution`, then a size of that group in `size`. The Random Chaos group also shows `max_aspect`.

### Inputs

| Input | Section | Default | Description |
|---|---|---|---|
| `resolution` | main | `Standard` | Group: `Standard`, `High-Res`, `Random` or `Random Chaos` (see below). |
| `size` | main | `1024 x 1024` | A size of the chosen group: a fixed size for Standard and High-Res, a list to pick from for Random, an orientation for Random Chaos (`Any`, `Portrait` or `Landscape`). |
| `max_aspect` | main (Random Chaos only) | `2.0` | The most stretched aspect ratio Random Chaos may pick (1.0–4.0): 2.0 means up to 2:1 or 1:2, 1.0 gives only squares. |
| `preview` | main | — | Live preview of the output size (width × height), the same widget as in the core *Resolution Selector*. It shows "—" for the random groups, because their size is only known at run time. |
| `seed` | main | `0` | Seed for the random options. The same seed always gives the same size. |
| `scale` | Advanced | `1.0` | Scales width and height by this factor (0.1–10), before rounding to `multiple`. Note that 2.0 gives 4x the pixels. |
| `multiple` | Advanced | `8` | Rounds width and height to the nearest multiple of this value (8–256, in steps of 8). Use 64 for SDXL training sizes. |
| `batch` | Advanced | `1` | Number of latents in the batch (1–32). |

### Outputs

| Output | Description |
|---|---|
| `latent` | Empty latent batch, identical to what **Empty Latent Image** makes for this size and `batch`. Connect it to the `latent_image` input of **KSampler**. |
| `width` | Width in pixels, for example for an upscale or hires-fix step. |
| `height` | Height in pixels. |
| `seed` | The seed used for this run, the same as the node's `seed` input. For example, connect it to the `seed` input of **KSampler**. |

### Fixed sizes

The `size` list shows width x height; the aspect ratios are given here for reference.

| Standard | High-Res |
|---|---|
| 1024 x 1024 (1:1) | 1536 x 1536 (1:1) |
| 1152 x 896 (9:7) / 896 x 1152 (7:9) | 1536 x 1152 (4:3) / 1152 x 1536 (3:4) |
| 1216 x 832 (3:2) / 832 x 1216 (2:3) | 1536 x 1024 (3:2) / 1024 x 1536 (2:3) |
| 1344 x 768 (16:9) / 768 x 1344 (9:16) | 1536 x 864 (16:9) / 864 x 1536 (9:16) |
| 1536 x 640 (21:9) / 640 x 1536 (9:21) | |

### Random groups

- **Random**: picks one of the listed sizes at random from the seed.
  - **Any Listed / Any High-Res Listed**: one of the Standard or High-Res sizes above.
  - **Vertical Listed / Horizontal Listed** (and their **High-Res** versions): only portrait or only landscape sizes.
- **Random Chaos**: a random aspect ratio up to `max_aspect`, at about 1024x1024 pixels (the SDXL native size; use `scale` for larger or smaller images).
  - **Any**: wide or tall, equally likely (the ratio is picked evenly in log scale).
  - **Portrait / Landscape**: only taller than wide, or only wider than tall; never a square.
  - The size rounds down to `multiple`, so it never exceeds 1024x1024 pixels before `scale` (it lands at about 0.9–1.0 of that).

### Notes

- Rounding to `multiple` applies to fixed sizes too. With the default 8 every listed size stays exact; with 64, 864 becomes 896.
- Like any `seed` input, it gets the frontend's *control after generate* option, which is *randomize* by default, so the random options give a new size on each run. Set it to *fixed* to keep the same size.

## Resolution Selector (Random, Latent)

Node id: `ResolutionSelectorRandomLatent`.

It works like the core ComfyUI *Resolution Selector* followed by **Empty Latent Image**, using the same size calculation, and adds random aspect ratios. For fixed ratios, the size is identical to the core node's.

### Inputs

| Input | Section | Default | Description |
|---|---|---|---|
| `aspect_ratio` | main | `1:1 (Square)` | A fixed ratio, or one of the random options below. |
| `megapixels` | main | `1.0` | Target total size (0.1–16). 1.0 MP = 1024x1024 for a square. |
| `preview` | main | — | Live preview of the output size and megapixels. It shows "—" for random options, because their size is only known at run time. |
| `seed` | main | `0` | Seed for the random options. By default it is randomized after each run (*control after generate*), so every run gets a new random ratio. Set it to *fixed* to repeat a result. |
| `multiple` | Advanced | `8` | Rounds width and height to the nearest multiple of this value (8–256, in steps of 8). Use 64 for SDXL training sizes. Random Chaos rounds down. |
| `batch` | Advanced | `1` | Number of latents in the batch (1–32). |
| `max_aspect` | Advanced | `2.0` | Random Chaos only: the most stretched ratio allowed (1.0–4.0). 2.0 means up to 2:1 or 1:2. |

### Outputs

| Output | Description |
|---|---|
| `latent` | Empty latent batch, identical to what **Empty Latent Image** makes for this size and `batch`. Connect it to the `latent_image` input of **KSampler**. |
| `width` | Width in pixels, for example for an upscale or hires-fix step. |
| `height` | Height in pixels. |
| `seed` | The seed used for this run, the same as the node's `seed` input. For example, connect it to the `seed` input of **KSampler**. |

### Aspect ratios

1:1, 2:3, 3:2, 3:4, 4:3, 7:9, 9:7, 9:16, 16:9, 9:21, 21:9.

### Random options

- **Random Any / Random Portrait / Random Landscape**: one of the listed ratios (any, only portrait or only landscape), each equally likely.
- **Random Chaos Any / Random Chaos Portrait / Random Chaos Landscape**: any ratio up to `max_aspect`. Wide and tall ratios are equally likely.

### Notes

- Fixed and Random ratios round to the nearest `multiple`, like the core node, so the size can be slightly above or below `megapixels` (about 0.94–1.06 at 1.0 MP).
- Random Chaos rounds down, so it never exceeds `megapixels` (it lands at about 0.9–1.0 of it), and Random Chaos Portrait/Landscape never return a square.

## About the latent

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
