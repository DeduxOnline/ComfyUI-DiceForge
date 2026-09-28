# ResolutionForge

ComfyUI nodes for both ends of a generation. Two of them output `width`, `height` and `batch` for an empty latent, and both can pick the canvas size at random from a seed. The third one decodes the finished latent and saves the image.

| Node | File | Use it when |
|---|---|---|
| **SDXL Resolution List** | `ResolutionForge/sdxl_resolution_list.py` | You want the standard SDXL sizes (1024x1024, 1216x832, ...) from a fixed list. |
| **Resolution Selector (Random)** | `ResolutionForge/resolution_selector_random.py` | You want to set an aspect ratio and a megapixel target, like the core *Resolution Selector* node. |
| **Load VAE + Decode + Save** | `ResolutionForge/vae_decode_save.py` | You want one node instead of *Load VAE*, *VAE Decode* and *Save Image*. |

All nodes are in the `utils` category. They use the ComfyUI V3 node schema: in the Nodes 2.0 frontend, the secondary inputs sit in the node's **Advanced** section.

## Installation

Copy the `ResolutionForge` folder into `ComfyUI/custom_nodes` and restart ComfyUI:

```sh
git clone https://github.com/DeduxOnline/unified_sdxl_res.git
cp -r unified_sdxl_res/ResolutionForge ComfyUI/custom_nodes/
```

Cloning the whole repository straight into `custom_nodes` does not work: the nodes are in the `ResolutionForge` subfolder, so ComfyUI does not find them.

`ResolutionForge/__init__.py` registers all nodes. To install only one of them, copy that `.py` file from `ResolutionForge` straight into `ComfyUI/custom_nodes` instead.

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

## Load VAE + Decode + Save

Node id: `LoadVAEDecodeSave`.

It does the work of three core nodes: *Load VAE*, *VAE Decode* and *Save Image*. Connect the sampler's `LATENT` output to it and pick the VAE.

### Inputs

| Input | Default | Description |
|---|---|---|
| `samples` | — | The latent to decode, for example the `LATENT` output of *KSampler*. |
| `vae_name` | — | The VAE to decode with. The list is the same as in the core *Load VAE* node, including `taesd` and `pixel_space`. |
| `filename_prefix` | `ComfyUI` | The prefix for the saved files, as in *Save Image*. A `/` makes a subfolder, for example `Anima/img`. It can include `%year%`, `%month%`, `%day%`, `%hour%`, `%minute%`, `%second%`, `%width%` and `%height%`. |

### Output

`images`: the decoded images, for further nodes such as an upscaler or a preview.

### Notes

- The files are PNGs in the ComfyUI output folder, with the prompt and the workflow as metadata, exactly as *Save Image* writes them.
- The node keeps the last VAE in memory, so it does not load the file again on every run. Picking another VAE replaces it.
- Decoding works as in *VAE Decode*. If the GPU runs out of memory, ComfyUI retries with tiled decoding by itself.
- `%date:yyyy-MM-dd%` and `%Node.widget%` tokens do not work in this node. The ComfyUI frontend replaces them only for its own save nodes. Use `%year%`, `%month%` and the other tokens above instead.

## Example workflows

The `workflows` folder has ComfyUI workflows that reproduce the defaults of [Forge Neo](https://github.com/Haoming02/sd-webui-forge-classic/tree/neo). The files are in API format: drag one onto the ComfyUI canvas to load it. After loading, select your own model files (and your own image in **Load Image**).

### Anima

They use the Forge Neo Anima preset: `er_sde` sampler, `beta` scheduler, 32 steps, CFG 4, shift 3. Shift 3 is already the Anima default in ComfyUI, so there is no ModelSampling node. The negative prompt is encoded as text, not zeroed out.

| File | What it does | Extra requirements |
|---|---|---|
| `anima_forge_neo_base.json` | Text to image. The size comes from **SDXL Resolution List** (`Any Listed`, about 1 MP). | None |
| `anima_forge_neo_edit.json` | Edits an image with an Anima Edit LoRA, like Forge Neo's *[Anima] Enable Reference* option. | [ComfyUI-Anima-Edit-LoRA](https://github.com/wochenlong/ComfyUI-Anima-Edit-LoRA) and an Anima Edit LoRA |

In the edit workflow:

- The source image is scaled to about 1 MP, with each side a multiple of 64, as Forge Neo does.
- The encoded image is used twice. It goes into **Set Reference Latent** on **both** the positive and the negative prompt, because Forge Neo also gives the reference to both. It is also the sampler's `latent_image`.
- At `denoise` 1.0 the sampler starts from pure noise, so the output simply has the same size as the reference. Lower `denoise` (for example 0.8) keeps more of the source composition, like the denoising strength in Forge Neo img2img.

### Illustrious and NoobAI (SDXL)

They use the Forge Neo XL preset: `euler_ancestral` sampler, `normal` scheduler (what *Automatic* gives for SDXL), 24 steps, CFG 4.5. Both need [ComfyUI_smZNodes](https://github.com/shiimizu/ComfyUI_smZNodes).

| File | For |
|---|---|
| `sdxl_forge_neo_eps.json` | Illustrious and NoobAI eps checkpoints |
| `sdxl_forge_neo_vpred.json` | NoobAI v-pred checkpoints and their merges |

What makes them behave like Forge Neo:

- Prompts go through **CLIP Text Encode++** with the `A1111` parser and `mean_normalization`. This gives the same weights as Forge's default *Original* emphasis, and supports `BREAK`, `AND`, `[tag]` and prompt editing such as `[a:b:0.5]`. For prompt editing, keep `smZ_steps` equal to the sampler steps.
- There is no **CLIP Set Last Layer** node. SDXL in ComfyUI already uses the penultimate CLIP layer, which is what Forge uses with Clip Skip 1 or 2. The node's default of -1 would switch to the last layer, which Forge never uses for SDXL.
- `with_SDXL` is off, so the size conditioning is the generation size with crop 0, as in Forge.
- The v-pred workflow forces `v_prediction` with ZTSNR through **ModelSamplingDiscrete**. Forge and ComfyUI both detect this from the `v_pred` and `ztsnr` keys in the file, but merges often lose those keys. **RescaleCFG** is set to 0 (off), the Forge default. Raise it if colors burn.
- The width and height are rounded to multiples of 64, like Forge's default resolution steps.
