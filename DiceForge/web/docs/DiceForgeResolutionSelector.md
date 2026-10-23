### Resolution Selector (Random)

![Resolution Selector (Random) in Nodes 2.0, 16:9 rescaled to a longest side of 1920](images/resolution_selector.png)

Node id: `DiceForgeResolutionSelector`.

It works like the core ComfyUI *Resolution Selector* followed by **Empty Latent Image**, using the same size calculation, and adds random aspect ratios. For fixed ratios, the size is identical to the core node's.

#### Inputs

| Input | Section | Default | Description |
|---|---|---|---|
| `aspect_ratio` | main | `1:1 (Square)` | A fixed ratio, or one of the random options below. |
| `megapixels` | main | `1.0` | Target total size (0.1–16). 1.0 MP = 1024x1024 for a square. |
| `preview` | main | — | Live preview of the output size and megapixels. Drawn in the Nodes 2.0 design only: in the classic canvas this core widget stays empty, in the core *Resolution Selector* too. For random options it shows the size of the last run, as long as the settings other than `seed` stay the same, and "—" before a run or after a change. |
| `seed` | main | `0` | Seed for the random options. By default it is randomized after each run (*control after generate*), so every run gets a new random ratio. Set it to *fixed* to repeat a result. |
| `multiple` | Advanced | `8` | Rounds width and height to the nearest multiple of this value (8–256, in steps of 8). Use 64 for SDXL training sizes. Random Chaos rounds down. |
| `batch` | Advanced | `1` | Number of latents in the batch (1–32). |
| `max_aspect` | Advanced | `2.0` | Random Chaos only: the most stretched ratio allowed (1.0–4.0). 2.0 means up to 2:1 or 1:2. |
| `seed_mode` | Advanced | `random` | How the random options change from run to run, as in SDXL Resolution List. See [Seed modes for sizes](https://github.com/DeduxOnline/ComfyUI-DiceForge#seed-modes-for-sizes). |
| `rescale` | main | `by percentage` | Rescales the size calculated from `aspect_ratio` and `megapixels`, with the same modes as in [SDXL Resolution List](https://github.com/DeduxOnline/ComfyUI-DiceForge#sdxl-resolution-list): `percent` of each side (150: 1:1 at 1 MP becomes 1536x1536), a `width` and/or `height` (0 follows the aspect ratio), or the `longer_side` (16:9 with 1920 becomes 1920x1080). Then each side is rounded to `multiple`. At 100% the size is exactly what it was without rescale; an API prompt without `rescale` gets 100%. |

#### Outputs

| Output | Description |
|---|---|
| `latent` | Empty latent batch, identical to what **Empty Latent Image** makes for this size and `batch`. Connect it to the `latent_image` input of **KSampler**. |
| `width` | Width in pixels, for example for an upscale or hires-fix step. |
| `height` | Height in pixels. |
| `seed` | The seed used for this run, the same as the node's `seed` input. For example, connect it to the `seed` input of **KSampler**. |

#### Aspect ratios

1:1, 2:3, 3:2, 3:4, 4:3, 7:9, 9:7, 9:16, 16:9, 9:21, 21:9.

#### Random options

- **Random Any / Random Portrait / Random Landscape**: one of the listed ratios (any, only portrait or only landscape), each equally likely.
- **Random Chaos Any / Random Chaos Portrait / Random Chaos Landscape**: any ratio up to `max_aspect`. Wide and tall ratios are equally likely.

#### Notes

- Fixed and Random ratios round to the nearest `multiple`, like the core node, so the size can be slightly above or below `megapixels` (about 0.94–1.06 at 1.0 MP).
- Random Chaos rounds down, so it never exceeds `megapixels` (it lands at about 0.9–1.0 of it), and Random Chaos Portrait/Landscape never return a square (unless `rescale` sets a square size, as in SDXL Resolution List).
