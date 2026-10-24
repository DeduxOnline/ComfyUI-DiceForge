Pick a resolution from the SDXL list (or at random from the seed) and output an empty latent of that size.

![SDXL Resolution List in Nodes 2.0, Advanced section open, rescaled by 150%](images/sdxl_resolution_list.png)

## Inputs

| Input | Type | Description |
|---|---|---|
| `resolution` | COMFY_DYNAMICCOMBO_V3 | Resolution group: fixed sizes, or random sizes picked from the seed. |
| `preview` (optional) | RESOLUTION_PREVIEW | Live preview of the output size. Random sizes show the size of the last run, until the settings change. |
| `seed` | INT | Seed for random resolution selection. |
| `rescale` | COMFY_DYNAMICCOMBO_V3 | Rescale the picked size, like HiresFix: by percentage of each side, to a width and/or height, or to a longest side. |

## Advanced inputs

Under **Show advanced inputs** on the node.

| Input | Type | Description |
|---|---|---|
| `multiple` | INT | Round width and height to a multiple of this value (8 for the VAE, 64 for SDXL training buckets). Random Chaos sizes round down. |
| `batch` | INT | Number of images to generate in a batch. |
| `seed_mode` | COMBO | How random sizes change from run to run. random: every pick is independent, so the same size can come up again soon. deck: the seed steps through a shuffled order; with control after generate on increment, every size comes once before any repeats. Reproducible. shuffle: like shuffle in a music player, the node remembers the sizes already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same size again. balanced: a size just picked gets a low chance, and sizes not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same size again. sequential: the seed is the position in the list, so seeds 0, 1, 2... go through the sizes in order. Reproducible. Random Chaos: the aspect range is split into equal parts that take turns (in order for sequential), with a random ratio inside each part. |

## Outputs

| Output | Type | Description |
|---|---|---|
| `latent` | LATENT | Empty latent batch, the same as Empty Latent Image makes for this size. |
| `width` | INT | Width of the latent in pixels. |
| `height` | INT | Height of the latent in pixels. |
| `seed` | INT | The seed used for this run, for example to pass on to KSampler. |

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#sdxl-resolution-list): examples, tips, and how it works with the other nodes.
