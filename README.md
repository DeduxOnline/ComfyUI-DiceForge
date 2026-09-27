# ResolutionForge

ComfyUI nodes for setting up a generation: two resolution nodes that output `width`, `height` and `batch` for an empty latent (both can pick the canvas size at random from a seed), their *Latent* versions that output the empty latent directly, and a prompt encoder that outputs positive and negative conditioning from one node.

| Node | File | Use it when |
|---|---|---|
| **SDXL Resolution List** | `ResolutionForge/sdxl_resolution_list.py` | You want the standard SDXL sizes (1024x1024, 1216x832, ...) from a fixed list. |
| **Resolution Selector (Random)** | `ResolutionForge/resolution_selector_random.py` | You want to set an aspect ratio and a megapixel target, like the core *Resolution Selector* node. |
| **SDXL Resolution List (Latent)** | `ResolutionForge/sdxl_resolution_list_latent.py` | Same as *SDXL Resolution List*, but you want the empty latent itself instead of connecting **Empty Latent Image**. |
| **Resolution Selector (Random, Latent)** | `ResolutionForge/resolution_selector_random_latent.py` | Same as *Resolution Selector (Random)*, but you want the empty latent itself. |
| **CLIP Text Encode (Positive/Negative)** | `ResolutionForge/clip_text_encode_pos_neg.py` | You want both prompts in one node instead of two *CLIP Text Encode (Prompt)* nodes. |

The resolution nodes are in the `utils` category, their *Latent* versions in `model/latent`, and the prompt encoder in `model/conditioning`. All nodes use the ComfyUI V3 node schema: in the Nodes 2.0 frontend, the secondary inputs of the resolution nodes sit in the node's **Advanced** section.

## Installation

Copy the `ResolutionForge` folder into `ComfyUI/custom_nodes` and restart ComfyUI:

```sh
git clone https://github.com/DeduxOnline/unified_sdxl_res.git
cp -r unified_sdxl_res/ResolutionForge ComfyUI/custom_nodes/
```

Cloning the whole repository straight into `custom_nodes` does not work: the nodes are in the `ResolutionForge` subfolder, so ComfyUI does not find them.

`ResolutionForge/__init__.py` registers all five nodes. To install only one of them, copy that `.py` file from `ResolutionForge` straight into `ComfyUI/custom_nodes` instead. This does not work for the *Latent* nodes: they reuse the code of their base resolution node, so install them with the whole folder.

**Requirements:** a recent ComfyUI that includes `comfy_api.latest` (the V3 node API). *Resolution Selector (Random)* also needs the resolution preview widget, which ships with the core *Resolution Selector* node. Older ComfyUI versions will not load these nodes.

## Typical use

- Connect `width`, `height` and `batch` of a resolution node to the `width`, `height` and `batch_size` inputs of **Empty Latent Image**.
- Or use a *Latent* version and connect its `latent` output straight to the `latent_image` input of **KSampler**.
- Connect the `CLIP` output of your checkpoint loader to **CLIP Text Encode (Positive/Negative)**, then its `positive` and `negative` outputs to the matching inputs of **KSampler**.

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

Like the output of **Empty Latent Image**, the latent works with any model you would use that node with: the core samplers adapt an empty latent to the model's latent format.

## CLIP Text Encode (Positive/Negative)

Node id: `CLIPTextEncodePositiveNegative`.

Works like two core *CLIP Text Encode (Prompt)* nodes sharing one CLIP model: each prompt is encoded exactly the same way, so the outputs are identical to the core node's.

### Inputs

| Input | Description |
|---|---|
| `clip` | The CLIP model used for encoding both prompts. |
| `positive` | The positive prompt (top text field): what the image should contain. |
| `negative` | The negative prompt (bottom text field): what the image should avoid. |

Both text fields support prompt weights such as `(word:1.2)` and dynamic prompts, like the core node.

### Outputs

| Output | Description |
|---|---|
| `positive` | Conditioning from the positive prompt. |
| `negative` | Conditioning from the negative prompt. |
