# Unified SDXL Resolution

Two ComfyUI nodes that output `width`, `height` and `batch` for an empty latent. Both can pick the canvas size at random from a seed.

| Node | File | Use it when |
|---|---|---|
| **SDXL Resolution List** | `sdxl_resolution_list.py` | You want the standard SDXL sizes (1024x1024, 1216x832, ...) from a fixed list. |
| **Resolution Selector (Random)** | `resolution_selector_random.py` | You want to set an aspect ratio and a megapixel target, like the core *Resolution Selector* node. |

Both nodes are in the `utils` category. They use the ComfyUI V3 node schema: in the Nodes 2.0 frontend, the secondary inputs sit in the node's **Advanced** section.

## Installation

Clone the repository into `ComfyUI/custom_nodes` and restart ComfyUI:

```sh
cd ComfyUI/custom_nodes
git clone https://github.com/DeduxOnline/unified_sdxl_res.git
```

`__init__.py` registers both nodes. To install only one of them, copy that `.py` file straight into `ComfyUI/custom_nodes` instead.

**Requirements:** a recent ComfyUI that includes `comfy_api.latest` (the V3 node API). *Resolution Selector (Random)* also needs the resolution preview widget, which ships with the core *Resolution Selector* node. Older ComfyUI versions will not load these nodes.

## Typical use

Connect `width`, `height` and `batch` to the `width`, `height` and `batch_size` inputs of **Empty Latent Image**.

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
- `seed` has no automatic increment on this node. Change it yourself, or connect a seed node, to get a new random size.

## Resolution Selector (Random)

Node id: `ResolutionSelectorRandom`.

It works like the core ComfyUI *Resolution Selector*, using the same size calculation, and adds random aspect ratios. For fixed ratios, its output is identical to the core node's.

### Inputs

| Input | Section | Default | Description |
|---|---|---|---|
| `aspect_ratio` | main | `1:1 (Square)` | A fixed ratio, or one of the random options below. |
| `megapixels` | main | `1.0` | Target total size (0.1–16). 1.0 MP = 1024x1024 for a square. |
| `preview` | main | — | Live preview of the output size. It shows "—" for random options, because their size is only known at run time. |
| `seed` | main | `0` | Seed for the random options. It changes after each run (`control_after_generate`), so every run gets a new random ratio. |
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
