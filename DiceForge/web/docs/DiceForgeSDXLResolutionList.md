Pick a resolution from the SDXL list (or at random from the seed) and output an empty latent of that size.

![SDXL Resolution List in Nodes 2.0, Advanced section open, rescaled by 150%](images/sdxl_resolution_list.png)

## Inputs

- `resolution` (COMBO): Resolution group: fixed sizes, or random sizes picked from the seed.
  - `size` (COMBO, default `1024 x 1024`, for Standard, High-Res, Random, Random Chaos): Standard SDXL size, width x height.
  - `max_aspect` (FLOAT, default `2`, for Random Chaos): The most stretched aspect ratio allowed (2.0 = up to 2:1 or 1:2).
- `preview` (RESOLUTION_PREVIEW): Live preview of the output size. Random sizes show the size of the last run, until the settings change.
- `seed` (INT, default `0`): Seed for random resolution selection.
- `rescale` (COMBO): Rescale the picked size, like HiresFix: by percentage of each side, to a width and/or height, or to a longest side.
  - `percent` (INT, default `100`, for by percentage): Each side in percent: 150 turns 1024x1024 into 1536x1536 (2.25 times the pixels), 50 into 512x512. Then rounded to multiple.
  - `width` (INT, default `1536`, for to Width/Height): The width. 0: follows the aspect ratio from the height.
  - `height` (INT, default `0`, for to Width/Height): The height. 0: follows the aspect ratio from the width. Both set: that exact size, whatever the size picked above.
  - `longer_side` (INT, default `1536`, for to longest side): The longest side of the size, keeping the aspect ratio: 1536 turns 1216x832 into 1536x1048 (rounded to multiple 8).

## Advanced inputs

Under **Show advanced inputs** on the node (Nodes 2.0), or **Show Advanced** in its right-click menu (classic design).

- `multiple` (INT, default `8`): Round width and height to a multiple of this value (8 for the VAE, 64 for SDXL training buckets). Random Chaos sizes round down.
- `batch` (INT, default `1`): Number of images to generate in a batch.
- `seed_mode` (COMBO, default `random`): How random sizes change from run to run. random: every pick is independent, so the same size can come up again soon. deck: the seed steps through a shuffled order; with control after generate on increment, every size comes once before any repeats. Reproducible. shuffle: like shuffle in a music player, the node remembers the sizes already used and picks from the rest with each new seed (increment or randomize); remembered in a file, so it continues after a restart. The same seed gives the same size again. balanced: a size just picked gets a low chance, and sizes not picked for a while get a higher one, so repeats are rare but possible. Remembered in a file. The same seed gives the same size again. sequential: the seed is the position in the list, so seeds 0, 1, 2... go through the sizes in order. Reproducible. Random Chaos: the aspect range is split into equal parts that take turns (in order for sequential), with a random ratio inside each part.

## Outputs

- `latent` (LATENT): Empty latent batch, the same as Empty Latent Image makes for this size.
- `width` (INT): Width of the latent in pixels.
- `height` (INT): Height of the latent in pixels.
- `seed` (INT): The seed used for this run, for example to pass on to KSampler.

More in the [DiceForge guide](https://github.com/DeduxOnline/ComfyUI-DiceForge#sdxl-resolution-list): examples, tips, and how it works with the other nodes.
